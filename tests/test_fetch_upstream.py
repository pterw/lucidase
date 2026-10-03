"""Offline tests for tools/fetch_upstream.py. No network access."""

import hashlib
import io
import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import fetch_upstream as fu
from tools.source_adapters import AdapterError

REAL = Path(__file__).resolve().parent.parent / "tools" / "fixtures" / "upstream" / "real"


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch):
    """No test here may reach the network (AGENTS.md section 6; the upstream fetch was approved once, in T2).

    Replaces urlopen, DNS and socket connect, so a test that forgets to pass an opener fails at once.
    """

    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


class FakeResp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_dbsnp_request_uses_numeric_id():
    spec = fu.dbsnp_request("rs429358")
    assert spec["url"] == "https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/429358"
    assert spec["method"] == "GET" and spec["body"] is None


def test_clinvar_requests():
    assert "term=rs671&" in fu.clinvar_esearch_request("rs671")["url"]
    assert "term=rs671%5BVariant+ID%5D" in fu.clinvar_esearch_request("rs671", tagged=True)["url"]
    url = fu.clinvar_esummary_request(["1", "2"])["url"]
    assert "esummary.fcgi?db=clinvar&id=1%2C2&retmode=json" in url
    with pytest.raises(ValueError):
        fu.clinvar_esummary_request([])


def test_vep_request_alphamissense_flag():
    on = fu.vep_request("rs7412")["url"]
    off = fu.vep_request("rs7412", alphamissense=False)["url"]
    assert on.startswith("https://rest.ensembl.org/vep/human/id/rs7412?content-type=application/json")
    assert "mane=1" in on and "canonical=1" in on and "hgvs=1" in on
    assert on.endswith("&AlphaMissense=1") and "AlphaMissense" not in off


def test_gnomad_requests_are_post_graphql():
    v = fu.gnomad_variant_request("rs6025")
    body = json.loads(v["body"])
    assert v["method"] == "POST" and v["url"] == "https://gnomad.broadinstitute.org/api"
    assert body["variables"] == {"rsid": "rs6025"} and "gnomad_r4" in body["query"]
    c = json.loads(fu.gnomad_constraint_request("F5")["body"])
    assert c["variables"] == {"symbol": "F5"} and "GRCh38" in c["query"] and "oe_lof_upper" in c["query"]


@pytest.mark.parametrize("bad", ["429358", "rsabc", "rs1; drop", ""])
def test_builders_reject_non_rsids(bad):
    with pytest.raises(ValueError):
        fu.dbsnp_request(bad)


def test_perform_sends_user_agent_and_body():
    seen = {}

    def opener(req, timeout):
        seen.update(ua=req.get_header("User-agent"), data=req.data, timeout=timeout, method=req.get_method())
        return FakeResp(200, b"{}")

    status, body = fu.perform(fu.gnomad_variant_request("rs671"), opener)
    assert (status, body) == (200, b"{}")
    assert seen["ua"] == fu.USER_AGENT and seen["timeout"] == 30 and seen["method"] == "POST"
    assert json.loads(seen["data"])["variables"]["rsid"] == "rs671"


def test_http_error_returns_status_and_payload():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":"x"}'))

    assert fu.perform(fu.dbsnp_request("rs671"), opener) == (400, b'{"error":"x"}')


def test_retry_happens_at_most_once_and_is_logged():
    calls, logs = [], []

    def opener(req, timeout):
        calls.append(1)
        return FakeResp(503, b"busy")

    status, _ = fu.perform_with_retry(fu.dbsnp_request("rs671"), opener, sleep=lambda s: None, log=logs.append)
    assert status == 503 and len(calls) == 2 and len(logs) == 1


def test_write_capture_verbatim_body_and_meta(tmp_path):
    body = b'{"a":   1,\r\n "b":[1,2]}'  # odd whitespace must survive byte-for-byte
    spec = fu.gnomad_variant_request("rs671")
    now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    meta = fu.write_capture(tmp_path, "gnomad", "rs671", spec, 200, body, now)
    assert (tmp_path / "gnomad" / "rs671.json").read_bytes() == body
    on_disk = json.loads((tmp_path / "gnomad" / "rs671.meta.json").read_text(encoding="utf-8"))
    assert on_disk == meta
    assert meta["sha256_of_body"] == hashlib.sha256(body).hexdigest()
    assert meta["bytes"] == len(body) and meta["http_status"] == 200
    assert meta["retrieved_at"] == "2026-10-02T12:00:00Z"
    assert meta["request_body"] == spec["body"] and meta["method"] == "POST" and meta["url"] == spec["url"]


def test_write_capture_failure_has_no_body_file(tmp_path):
    meta = fu.write_capture(tmp_path, "dbsnp", "rs1", fu.dbsnp_request("rs1"), 404, b"nope")
    assert not (tmp_path / "dbsnp" / "rs1.json").exists()
    assert meta["http_status"] == 404 and meta["sha256_of_body"] is None and meta["bytes"] == 0


def test_cap_aborts_when_total_exceeds_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(fu, "MAX_TOTAL_BYTES", 10)
    cap = fu.Capturer(tmp_path, opener=lambda req, timeout: FakeResp(200, b"x" * 11), sleep=lambda s: None, log=lambda m: None)
    with pytest.raises(fu.CapBytesExceeded):
        cap.run("dbsnp", "rs1", fu.dbsnp_request("rs1"))


def test_capturer_sleeps_between_requests(tmp_path):
    sleeps = []
    cap = fu.Capturer(tmp_path, opener=lambda req, timeout: FakeResp(200, b"{}"), sleep=sleeps.append, log=lambda m: None)
    cap.run("dbsnp", "rs1", fu.dbsnp_request("rs1"))
    assert sleeps and min(sleeps) >= 0.4


def test_committed_fixtures_match_their_sha256():
    metas = sorted(REAL.rglob("*.meta.json"))
    assert metas, "no committed upstream fixtures found"
    checked = 0
    for meta_path in metas:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        stem = meta_path.name[: -len(".meta.json")]
        body_path = meta_path.with_name(stem if stem.endswith(".gz") else stem + ".json")  # UCSC bodies are gzip
        if meta["sha256_of_body"] is None:
            assert not body_path.exists(), f"{body_path} exists but meta records no body"
            continue
        data = body_path.read_bytes()
        assert len(data) == meta["bytes"], f"{body_path}: byte count differs from meta"
        assert hashlib.sha256(data).hexdigest() == meta["sha256_of_body"], f"{body_path}: sha256 mismatch"
        checked += 1
    assert checked > 0
    for body_path in REAL.rglob("*.json"):
        if not body_path.name.endswith(".meta.json"):
            assert body_path.with_name(body_path.stem + ".meta.json").exists(), f"{body_path} has no meta"


def test_gnomad_variant_id_request_and_validation():
    body = json.loads(fu.gnomad_variant_id_request("10-94781859-G-A")["body"])
    assert body["variables"] == {"variantId": "10-94781859-G-A"} and "variantId" in body["query"]
    with pytest.raises(ValueError):
        fu.gnomad_variant_id_request("10-abc-G-A")


def test_multiallelic_fallback_queries_each_alt_by_variant_id(tmp_path):
    """Real rs4244285 captures: the gnomAD refusal and the dbSNP placements drive one query per alt allele."""
    for source in ("gnomad", "dbsnp"):
        (tmp_path / source).mkdir()
        (tmp_path / source / "rs4244285.json").write_bytes((REAL / source / "rs4244285.json").read_bytes())
    seen = []

    def opener(req, timeout):
        seen.append(json.loads(req.data)["variables"]["variantId"])
        return FakeResp(200, b"{}")

    cap = fu.Capturer(tmp_path, opener=opener, sleep=lambda s: None, log=lambda m: None)
    fu.capture_gnomad_multiallelic(cap, rsids=("rs4244285",))
    assert seen == ["10-94781859-G-A", "10-94781859-G-C", "10-94781859-G-T"]
    assert (tmp_path / "gnomad" / "rs4244285.10-94781859-G-C.json").exists()


def test_multiallelic_detection_ignores_a_biallelic_capture_and_rejects_garbage(tmp_path):
    (tmp_path / "gnomad").mkdir()
    (tmp_path / "gnomad" / "rs671.json").write_bytes((REAL / "gnomad" / "rs671.json").read_bytes())
    cap = fu.Capturer(tmp_path, opener=lambda req, timeout: pytest.fail("no request expected"), sleep=lambda s: None, log=lambda m: None)
    fu.capture_gnomad_multiallelic(cap, rsids=("rs671",))
    (tmp_path / "gnomad" / "rs1.json").write_bytes(b"<html>502</html>")
    with pytest.raises(AdapterError):
        fu.capture_gnomad_multiallelic(cap, rsids=("rs1",))


def _esearch_body(count, uids):
    return json.dumps({"esearchresult": {"count": str(count), "idlist": uids}}).encode()


def test_esearch_request_sets_explicit_retmax():
    assert "retmax=500" in fu.clinvar_esearch_request("rs4244285")["url"]


def test_truncated_esearch_fails_closed(tmp_path):
    def opener(req, timeout):
        return FakeResp(200, _esearch_body(37, [str(i) for i in range(20)]))

    cap = fu.Capturer(tmp_path, opener=opener, sleep=lambda s: None, log=lambda m: None)
    with pytest.raises(fu.TruncatedSearch):
        fu.capture_clinvar(cap, "rs4244285")


def _router(routes, seen):
    def opener(req, timeout):
        seen.append(req.full_url)
        for needle, resp in routes:
            if needle in req.full_url:
                return resp() if callable(resp) else resp
        raise AssertionError(req.full_url)

    return opener


def test_clinvar_handoff_and_tagged_fallback(tmp_path):
    seen = []
    routes = [
        ("esearch.fcgi?db=clinvar&term=rs1%5B", FakeResp(200, _esearch_body(2, ["7", "9"]))),
        ("esearch.fcgi", FakeResp(200, _esearch_body(0, []))),
        ("esummary.fcgi", FakeResp(200, b'{"result":{}}')),
    ]
    cap = fu.Capturer(tmp_path, opener=_router(routes, seen), sleep=lambda s: None, log=lambda m: None)
    fu.capture_clinvar(cap, "rs1")
    assert any("id=7%2C9" in u for u in seen)
    assert (tmp_path / "clinvar" / "rs1.json").exists()
    assert (tmp_path / "clinvar" / "rs1.esearch_tagged.json").exists()


def test_vep_400_keeps_error_and_retries_without_alphamissense(tmp_path):
    seen = []

    def opener(req, timeout):
        seen.append(req.full_url)
        if "rest.ensembl.org" in req.full_url:
            if "AlphaMissense" in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":"AlphaMissense"}'))
            return FakeResp(200, b"[]")
        if "esearch" in req.full_url:
            return FakeResp(200, _esearch_body(0, []))
        return FakeResp(200, b"{}")

    cap = fu.Capturer(tmp_path, opener=opener, sleep=lambda s: None, log=lambda m: None)
    fu.capture_all(cap, rsids=("rs671",), genes=())
    rejected = json.loads((tmp_path / "ensembl" / "rs671.alphamissense_rejected.meta.json").read_text())
    assert rejected["http_status"] == 400 and "AlphaMissense" in rejected["error_payload"]
    assert (tmp_path / "ensembl" / "rs671.json").read_bytes() == b"[]"
    assert "AlphaMissense" not in [u for u in seen if "rest.ensembl.org" in u][-1]


@pytest.mark.parametrize("status,expected_calls", [(429, 2), (0, 2), (404, 1), (200, 1)])
def test_retry_policy_by_status(status, expected_calls):
    calls = []

    def opener(req, timeout):
        calls.append(1)
        if status == 0:
            raise urllib.error.URLError("down")
        return FakeResp(status, b"x") if status < 400 else (_ for _ in ()).throw(
            urllib.error.HTTPError(req.full_url, status, "e", {}, io.BytesIO(b"x"))
        )

    fu.perform_with_retry(fu.dbsnp_request("rs1"), opener, sleep=lambda s: None, log=lambda m: None)
    assert len(calls) == expected_calls


# ---------------------------------------------------------------------------
# S3-F2a: a failed request fails the run
# ---------------------------------------------------------------------------
def _http_error(req, status, body=b"x"):
    return urllib.error.HTTPError(req.full_url, status, "e", {}, io.BytesIO(body))


def _quiet_capturer(tmp_path, opener):
    return fu.Capturer(tmp_path, opener=opener, sleep=lambda s: None, log=lambda m: None)


@pytest.mark.parametrize("status", [404, 500, 503, 429])
def test_final_non_200_raises_capture_failed_and_keeps_the_failure_meta(tmp_path, status):
    def opener(req, timeout):
        raise _http_error(req, status)

    cap = _quiet_capturer(tmp_path, opener)
    with pytest.raises(fu.CaptureFailed) as info:
        cap.run("dbsnp", "rs1", fu.dbsnp_request("rs1"))
    assert (info.value.source, info.value.key, info.value.status) == ("dbsnp", "rs1", status)
    assert json.loads((tmp_path / "dbsnp" / "rs1.meta.json").read_text())["http_status"] == status


def test_transport_failure_and_empty_200_body_fail_too(tmp_path):
    def down(req, timeout):
        raise urllib.error.URLError("down")

    with pytest.raises(fu.CaptureFailed) as info:
        _quiet_capturer(tmp_path, down).run("dbsnp", "rs1", fu.dbsnp_request("rs1"))
    assert info.value.status == 0
    with pytest.raises(fu.CaptureFailed):
        _quiet_capturer(tmp_path, lambda req, timeout: FakeResp(200, b"")).run("dbsnp", "rs2", fu.dbsnp_request("rs2"))


def test_a_200_does_not_raise(tmp_path):
    status, body, _ = _quiet_capturer(tmp_path, lambda req, timeout: FakeResp(200, b"{}")).run(
        "dbsnp", "rs1", fu.dbsnp_request("rs1")
    )
    assert (status, body) == (200, b"{}")


def test_esearch_500_is_a_failure_not_zero_uids(tmp_path):
    seen = []

    def opener(req, timeout):
        seen.append(req.full_url)
        raise _http_error(req, 500)

    with pytest.raises(fu.CaptureFailed) as info:
        fu.capture_clinvar(_quiet_capturer(tmp_path, opener), "rs671")
    assert info.value.key == "rs671.esearch" and info.value.status == 500
    assert not any("esummary" in u or "Variant+ID" in u or "Variant%20ID" in u or "%5BVariant" in u for u in seen)


@pytest.mark.parametrize("body", [b"{}", b"not json", b'{"esearchresult": {"count": "1"}}'])
def test_malformed_esearch_body_raises_instead_of_meaning_no_hits(tmp_path, body):
    cap = _quiet_capturer(tmp_path, lambda req, timeout: FakeResp(200, body))
    with pytest.raises(AdapterError):
        fu.capture_clinvar(cap, "rs671")


def test_truncated_search_is_the_adapters_exception():
    from tools.source_adapters import TruncatedSearch

    assert fu.TruncatedSearch is TruncatedSearch and issubclass(fu.TruncatedSearch, AdapterError)


def test_vep_400_is_tolerated_once_but_the_retry_must_succeed(tmp_path):
    def opener(req, timeout):
        if "rest.ensembl.org" in req.full_url:
            raise _http_error(req, 400, b'{"error":"AlphaMissense"}')
        if "esearch" in req.full_url:
            return FakeResp(200, _esearch_body(0, []))
        return FakeResp(200, b"{}")

    cap = _quiet_capturer(tmp_path, opener)
    fu.capture_all(cap, rsids=("rs671",), genes=())
    assert [(f.source, f.key, f.status) for f in cap.failures] == [("ensembl", "rs671", 400)]
    assert (tmp_path / "ensembl" / "rs671.alphamissense_rejected.meta.json").exists()


def test_capture_all_keeps_going_after_a_failure_and_lists_every_failed_key(tmp_path):
    def opener(req, timeout):
        url = req.full_url
        posted = (req.data or b"").decode()
        if "refsnp/429358" in url or '"symbol":"APOE"' in posted:
            raise _http_error(req, 500)
        if "esearch" in url:
            return FakeResp(200, _esearch_body(0, []))
        return FakeResp(200, b"{}")

    cap = _quiet_capturer(tmp_path, opener)
    fu.capture_all(cap, rsids=("rs429358", "rs671"), genes=("APOE", "F5"))
    assert [(f.source, f.key) for f in cap.failures] == [("dbsnp", "rs429358"), ("gnomad", "constraint_APOE")]
    assert (tmp_path / "dbsnp" / "rs671.json").exists()  # the second rsID was still captured
    assert (tmp_path / "gnomad" / "constraint_F5.json").exists()


def test_main_exits_1_and_lists_the_failed_keys(tmp_path, capsys):
    def opener(req, timeout):
        if "term=rs671&" in req.full_url:
            raise _http_error(req, 500)
        if "esearch" in req.full_url:
            return FakeResp(200, _esearch_body(1, ["5"]))
        return FakeResp(200, b'{"result": {}}')

    code = fu.main(["--out", str(tmp_path), "--clinvar-only", "rs671", "rs1801133"], opener=opener, sleep=lambda s: None)
    err = capsys.readouterr().err
    assert code == 1
    assert "clinvar/rs671.esearch: HTTP 500" in err
    assert (tmp_path / "clinvar" / "rs1801133.json").exists()  # the run kept going


def test_main_exits_0_when_every_request_succeeds(tmp_path):
    def opener(req, timeout):
        if "esearch" in req.full_url:
            return FakeResp(200, _esearch_body(1, ["5"]))
        return FakeResp(200, b"{}")

    assert fu.main(["--out", str(tmp_path), "--clinvar-only", "rs671"], opener=opener, sleep=lambda s: None) == 0


def test_main_exits_2_on_a_truncated_search(tmp_path, capsys):
    opener = lambda req, timeout: FakeResp(200, _esearch_body(37, ["1", "2"]))  # noqa: E731
    code = fu.main(["--out", str(tmp_path), "--clinvar-only", "rs671"], opener=opener, sleep=lambda s: None)
    assert code == 2 and "truncated" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# S3-F2a (review S3a-C-10, C-14): TLS stays on, the recorded URL is the requested one, the guard works
# ---------------------------------------------------------------------------
def test_the_offline_guard_stops_a_request_with_no_opener():
    """The default opener is resolved at call time, so the guard catches a test that forgets to pass one."""
    with pytest.raises(AssertionError, match="network access attempted"):
        fu.perform(fu.dbsnp_request("rs671"))


def test_every_request_spec_is_https():
    specs = [fu.dbsnp_request("rs1"), fu.clinvar_esearch_request("rs1"), fu.clinvar_esearch_request("rs1", True),
             fu.clinvar_esummary_request(["1"]), fu.vep_request("rs1"), fu.gnomad_variant_request("rs1"),
             fu.gnomad_variant_id_request("1-5-C-A"), fu.gnomad_constraint_request("F5")]
    assert all(spec["url"].startswith("https://") for spec in specs)


def test_perform_passes_only_a_timeout_so_certificate_verification_stays_default():
    seen = {}

    def opener(req, **kwargs):
        seen.update(kwargs)
        return FakeResp(200, b"{}")

    fu.perform(fu.dbsnp_request("rs1"), opener)
    assert set(seen) == {"timeout"}, "an SSL context argument would be the only way to weaken verification"
    assert not hasattr(fu, "ssl")


def test_the_recorded_url_is_the_requested_url_on_disk(tmp_path):
    spec = fu.clinvar_esearch_request("rs671")
    _quiet_capturer(tmp_path, lambda req, timeout: FakeResp(200, b"{}")).run("clinvar", "rs671.esearch", spec)
    meta = json.loads((tmp_path / "clinvar" / "rs671.esearch.meta.json").read_text())
    assert meta["url"] == spec["url"] and meta["url"].startswith("https://eutils.ncbi.nlm.nih.gov/")


# ---------------------------------------------------------------------------
# UCSC assembly geometry capture (karyogram K1)
# ---------------------------------------------------------------------------
UCSC_URLS = [
    "https://hgdownload.soe.ucsc.edu/goldenPath/hg19/database/chromInfo.txt.gz",
    "https://hgdownload.soe.ucsc.edu/goldenPath/hg19/database/cytoBand.txt.gz",
    "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/chromInfo.txt.gz",
    "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/cytoBand.txt.gz",
]


def test_ucsc_capture_requests_exactly_the_four_approved_urls():
    specs = fu.ucsc_requests()
    assert [spec["url"] for _, spec in specs] == UCSC_URLS
    assert [key for key, _ in specs] == [
        "hg19.chromInfo.txt.gz",
        "hg19.cytoBand.txt.gz",
        "hg38.chromInfo.txt.gz",
        "hg38.cytoBand.txt.gz",
    ]
    assert all(spec["method"] == "GET" and spec["body"] is None for _, spec in specs)


def test_ucsc_capture_writes_the_gzip_body_verbatim_with_meta(tmp_path):
    body = b"\x1f\x8b\x08\x00fake gzip bytes"
    seen = []

    def opener(req, timeout):
        seen.append(req.full_url)
        return FakeResp(200, body)

    cap = fu.Capturer(tmp_path, opener=opener, sleep=lambda s: None, log=lambda m: None)
    fu.capture_ucsc(cap)
    assert seen == UCSC_URLS
    written = tmp_path / "ucsc" / "hg19.chromInfo.txt.gz"
    assert written.read_bytes() == body
    meta = json.loads((tmp_path / "ucsc" / "hg19.chromInfo.txt.gz.meta.json").read_text(encoding="utf-8"))
    assert meta["url"] == UCSC_URLS[0]
    assert meta["sha256_of_body"] == hashlib.sha256(body).hexdigest()
    assert meta["bytes"] == len(body) and meta["http_status"] == 200


def test_ucsc_capture_fails_on_a_non_200_response(tmp_path):
    seen = []

    def opener(req, timeout):
        seen.append(req.full_url)
        return FakeResp(404, b"not found")

    cap = fu.Capturer(tmp_path, opener=opener, sleep=lambda s: None, log=lambda m: None)
    with pytest.raises(fu.UcscCaptureFailed, match="chromInfo.txt.gz: HTTP 404"):
        fu.capture_ucsc(cap)
    assert seen == UCSC_URLS[:1]  # stops at the first failure


def test_ucsc_capture_names_an_empty_200_body_as_empty(tmp_path):
    def opener(req, timeout):
        return FakeResp(200, b"")

    cap = fu.Capturer(tmp_path, opener=opener, sleep=lambda s: None, log=lambda m: None)
    with pytest.raises(fu.UcscCaptureFailed, match="chromInfo.txt.gz: empty response body") as info:
        fu.capture_ucsc(cap)
    assert "HTTP 200" not in str(info.value)


def test_ucsc_only_cli_runs_only_the_ucsc_capture(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fu, "capture_ucsc", lambda cap: calls.append("ucsc"))
    monkeypatch.setattr(fu, "capture_all", lambda cap: calls.append("all"))
    assert fu.main(["--out", str(tmp_path), "--ucsc-only"]) == 0
    assert calls == ["ucsc"]
