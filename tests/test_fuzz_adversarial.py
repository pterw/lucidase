import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genomic_parser import GenomicParser
from variant_annotator import VariantAnnotator

samples = {
    "1_empty_file": "",
    "2_only_newlines": "\n" * 500,
    "3_corrupted_headers": "# build 37\n# rsid\tchr\tpos\tgenotype\n" + "\t".join(["invalid"] * 20),
    "4_binary_null_bytes": "\x00\x00\x00\xff\xfe\x00\x1b\x5b",
    "5_html_error_page": "<html><head><title>500 Internal Server Error</title></head><body>Crash</body></html>",
    "6_json_payload": json.dumps({"user": "victim", "dna": [1, 2, 3]}),
    "7_sql_injection": "rs123\t1\t100\t'; DROP TABLE users; --\nrs456\t' OR '1'='1\t200\tAA",
    "8_massive_single_line": "rs429358\t19\t45411941\tCC\t" + ("A" * 200000),
    "9_non_standard_chrom": "rs1\tchrUn_gl000220\t1000\tAA\nrs2\tM\t200\tCC\nrs3\t25\t300\tGG",
    "10_mixed_corrupt_and_valid": (
        "# 23andMe sample with corruption\n"
        "rubbish line\n"
        "rs429358\t19\t45411941\tCC\n"
        "bad\t\t\t\n"
        "rs7412\t19\t45412079\tCC\n"
        "rs1800562\t6\t26093141\tAG\n"
    )
}

annotator = VariantAnnotator()

print("=== ADVERSARIAL STRESS TEST RESULTS ===")
for name, data in samples.items():
    try:
        calls, qc = GenomicParser.parse_text(data)
        annotated = annotator.annotate_genome(calls)
        print(f"{name:<28} | STATUS: OK | Calls: {len(calls):<4} | Annotated: {len(annotated):<3} | Build: {qc.build:<6} | Sex: {qc.inferred_sex}")
    except Exception as e:
        print(f"{name:<28} | STATUS: FAILED ({type(e).__name__}): {e}")
