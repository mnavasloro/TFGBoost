import threading
import time

from app.llm import LLMError
from app.services.pipeline import analyse_document
from app.services.trace import Trace, read_trace
from tests.conftest import SAMPLE_TFG, FakeProvider


class SlowProvider(FakeProvider):
    """Registra cuándo empieza y termina cada llamada; tarda 0,2 s por llamada."""

    def __init__(self, parallel: int, fail_calls=()):
        super().__init__()
        self.parallel_requests = parallel
        self.fail_calls = set(fail_calls)
        self.spans = []
        self.lock = threading.Lock()
        self.counter = 0

    def complete_json(self, system, document, instructions, schema):
        with self.lock:
            self.counter += 1
            number = self.counter
        start = time.perf_counter()
        time.sleep(0.2)
        with self.lock:
            self.spans.append((start, time.perf_counter()))
        if number in self.fail_calls:
            raise LLMError(f"fallo simulado {number}")
        with self.lock:  # FakeProvider no es seguro entre hilos
            return super().complete_json(system, document, instructions, schema)


def _comparable(report):
    return [(i["id"], i["status"], [c["quote"] for c in i["comments"]]) for i in report["items"]]


def test_first_call_alone_then_the_rest_in_parallel(tmp_path):
    provider = SlowProvider(parallel=4)
    started = time.perf_counter()
    report = analyse_document(SAMPLE_TFG, "tfg.docx", "p", provider, trace=Trace(tmp_path, "p"))
    elapsed = time.perf_counter() - started
    spans = sorted(provider.spans)
    assert len(spans) == 5
    assert all(start >= spans[0][1] for start, _ in spans[1:])  # la primera termina antes de lanzar las demás
    assert max(start for start, _ in spans[1:]) < min(end for _, end in spans[1:])  # las otras 4 se solapan
    assert elapsed < 0.2 * 5 * 0.7  # claramente más rápido que en secuencia (~1 s)
    timing = next(e for e in read_trace(tmp_path, "p") if e["event"] == "llm_timing")
    assert timing["parallel_requests"] == 4 and timing["wall_seconds"] < 0.7
    sequential = analyse_document(SAMPLE_TFG, "tfg.docx", "s", SlowProvider(parallel=1))
    assert _comparable(report) == _comparable(sequential)  # mismo resultado, mismo orden
    assert report["usage"]["calls"] == sequential["usage"]["calls"]  # mismo número de llamadas (mismo coste)


def test_two_initial_failures_stop_before_fanning_out():
    provider = SlowProvider(parallel=4, fail_calls={1, 2})
    report = analyse_document(SAMPLE_TFG, "tfg.docx", "f", provider)
    assert len(provider.spans) == 2  # no se lanzan las otras 3 peticiones
    assert sum("omitido" in e for e in report["llm_errors"]) == 3


def test_failure_after_warm_up_does_not_stop_the_others():
    provider = SlowProvider(parallel=4, fail_calls={3})
    report = analyse_document(SAMPLE_TFG, "tfg.docx", "g", provider)
    assert len(provider.spans) == 5 and len(report["llm_errors"]) == 1


def test_providers_without_cache_send_everything_at_once():
    provider = SlowProvider(parallel=4)
    provider.cache_warmup = False  # como OpenRouter
    analyse_document(SAMPLE_TFG, "tfg.docx", "o", provider)
    spans = sorted(provider.spans)
    assert spans[1][0] < spans[0][1]  # la segunda empieza antes de que termine la primera
