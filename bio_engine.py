"""
Bio Engine: Biopython Integration for De Bruijn Graph & Sequence Assembly
========================================================================
Handles FASTA/FASTQ/GenBank/EMBL parsing, sequence manipulation (reverse complements),
GC fraction calculation, molecular weight calculation, Open Reading Frame (ORF) / 6-frame
translation, Biopython SeqRecord generation with annotated CDS features, and pairwise
reference alignment evaluation using Bio.Align.PairwiseAligner.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from Bio import SeqIO
from Bio.Align import PairwiseAligner
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord
from Bio.SeqUtils import gc_fraction, molecular_weight

MAX_LOAD_CHARS = 60_000


def revcomp(seq: str) -> str:
    """Return the reverse complement of a DNA sequence using Biopython."""
    return str(Seq(seq).reverse_complement())


def parse_records(text: str) -> list[str]:
    """FASTA-aware parser: with '>' headers, wrapped lines join into one record;
    without headers, every non-empty line is treated as its own sequence."""
    lines = [ln.strip() for ln in text.splitlines()]
    if any(ln.startswith(">") for ln in lines):
        records: list[list[str]] = []
        cur: list[str] | None = None
        for ln in lines:
            if not ln:
                continue
            if ln.startswith(">"):
                cur = []
                records.append(cur)
            else:
                if cur is None:
                    cur = []
                    records.append(cur)
                cur.append(ln)
        return ["".join(r).upper() for r in records if r]
    return [re.sub(r"\s+", "", ln).upper() for ln in lines if ln]


def load_sequences_as_fasta(path: str) -> tuple[str, str]:
    """Read FASTA / FASTQ / GenBank / EMBL with Biopython -> (fasta_text, note)."""
    ext = os.path.splitext(path)[1].lower()
    fmt = {
        ".fq": "fastq",
        ".fastq": "fastq",
        ".gb": "genbank",
        ".gbk": "genbank",
        ".genbank": "genbank",
        ".embl": "embl",
    }.get(ext, "fasta")
    parts, total, count, truncated = [], 0, 0, False
    for rec in SeqIO.parse(path, fmt):
        s = str(rec.seq).upper()
        if total + len(s) > MAX_LOAD_CHARS:
            truncated = True
            break
        parts.append(f">{rec.id}\n{s}")
        total += len(s)
        count += 1
    if not parts:
        raise ValueError(
            f"No usable {fmt.upper()} records found (or the first one exceeds "
            f"{MAX_LOAD_CHARS:,} bases)."
        )
    note = f"Loaded {count} record(s) from {os.path.basename(path)} ({fmt})."
    if truncated:
        note += f" Stopped at {MAX_LOAD_CHARS:,} bases; later records were not loaded."
    return "\n".join(parts), note


def _gc_content(seq: str) -> float:
    """GC fraction of a DNA sequence calculated via Biopython."""
    if not seq:
        return 0.0
    try:
        return round(float(gc_fraction(Seq(seq))), 4)
    except Exception:
        gc = sum(1 for c in seq.upper() if c in "GC")
        return round(gc / len(seq), 4)


def safe_mw(seq: str) -> float:
    """Molecular weight (Da) calculated via Biopython for DNA sequences."""
    try:
        seq_u = seq.upper()
        if seq_u and set(seq_u).issubset(set("ACGT")):
            return round(float(molecular_weight(Seq(seq_u), "DNA")), 1)
        return 0.0
    except Exception:
        return 0.0


def find_orfs(seq: str, min_aa_len: int = 10) -> list[dict]:
    """Identify Open Reading Frames (ORFs) across all 6 frames using Biopython.

    Searches forward (+1, +2, +3) and reverse complement (-1, -2, -3) strands
    for start codons (ATG) and in-frame stop codons (TAA, TAG, TGA). Translates
    detected coding sequences into amino acid sequences using Bio.Seq.translate."""
    seq_u = seq.upper()
    if not seq_u or not set(seq_u).issubset(set("ACGTN")):
        return []
    orfs = []
    strands = [(seq_u, +1), (str(Seq(seq_u).reverse_complement()), -1)]
    for s_seq, strand in strands:
        n = len(s_seq)
        for frame in range(3):
            for i in range(frame, n - 2, 3):
                codon = s_seq[i : i + 3]
                if codon == "ATG":
                    for j in range(i + 3, n - 2, 3):
                        stop_codon = s_seq[j : j + 3]
                        if stop_codon in ("TAA", "TAG", "TGA"):
                            aa_len = (j - i) // 3
                            if aa_len >= min_aa_len:
                                nt_sub = s_seq[i : j + 3]
                                aa_seq = str(Seq(nt_sub).translate(to_stop=True))
                                if strand == +1:
                                    start_pos, end_pos = i, j + 3
                                else:
                                    start_pos, end_pos = n - (j + 3), n - i
                                orfs.append({
                                    "strand": strand,
                                    "frame": frame + 1 if strand == 1 else -(frame + 1),
                                    "start": start_pos,
                                    "end": end_pos,
                                    "length_nt": len(nt_sub),
                                    "length_aa": len(aa_seq),
                                    "protein": aa_seq,
                                })
                            break
    return orfs


def contigs_to_seqrecords(contigs: list[dict]) -> list[SeqRecord]:
    """Convert assembled contigs into Biopython SeqRecord objects with rich metadata."""
    records = []
    for c in contigs:
        seq_str = c["sequence"]
        orf_list = c.get("orfs", [])
        desc = (
            f"len={c['length']} cov={c['mean_coverage']:.1f}x "
            f"gc={c['gc_content']:.3f} bin={c.get('bin_id', 1)} "
            f"orfs={len(orf_list)}"
        )
        if c.get("is_outlier"):
            desc += " outlier=true"
        rec = SeqRecord(Seq(seq_str), id=f"ctg{c['id']}", name=f"ctg{c['id']}", description=desc)
        rec.annotations["molecule_type"] = "DNA"
        rec.annotations["topology"] = "circular" if c.get("circular") else "linear"
        for orf in orf_list:
            feat = SeqFeature(
                FeatureLocation(orf["start"], orf["end"], strand=orf["strand"]),
                type="CDS",
                qualifiers={
                    "translation": [orf["protein"]],
                    "product": ["predicted open reading frame"],
                    "frame": [str(orf["frame"])],
                    "codon_start": [1],
                },
            )
            rec.features.append(feat)
        records.append(rec)
    return records


def write_contigs_fasta(contigs: list[dict], path: str) -> None:
    """Write assembled contigs as FASTA using Biopython SeqIO."""
    records = contigs_to_seqrecords(contigs)
    with open(path, "w", encoding="utf-8") as f:
        SeqIO.write(records, f, "fasta")


def write_contigs_genbank(contigs: list[dict], path: str) -> None:
    """Write assembled contigs with annotated ORFs as GenBank using Biopython SeqIO."""
    records = contigs_to_seqrecords(contigs)
    with open(path, "w", encoding="utf-8") as f:
        SeqIO.write(records, f, "genbank")


def evaluate_assembly_against_reference(contigs: list[dict], ref_seq: str) -> dict:
    """Evaluate assembly fidelity against a reference genome using Biopython PairwiseAligner."""
    if not contigs or not ref_seq:
        return {"reference_length": len(ref_seq), "genome_fraction": 0.0, "aligned_contigs": 0}
    aligner = PairwiseAligner()
    aligner.mode = "local"
    aligner.match_score = 1
    aligner.mismatch_score = -1
    aligner.open_gap_score = -2
    aligner.extend_gap_score = -1

    ref_u = ref_seq.upper()
    covered_positions = set()
    total_matches = 0
    total_aligned_bases = 0
    contig_reports = []

    for c in contigs:
        seq = c["sequence"].upper()
        if len(seq) < 5:
            continue
        try:
            alignments = aligner.align(ref_u, seq)
            if not alignments:
                continue
            best = alignments[0]
            if best.score <= 0:
                continue
            t_coords = best.aligned[0]
            q_coords = best.aligned[1]
            aln_len = sum(end - start for start, end in q_coords)
            for start, end in t_coords:
                for pos in range(start, end):
                    covered_positions.add(pos)
            ident = round(min(1.0, max(0.0, best.score / aln_len)), 3) if aln_len else 0.0
            total_aligned_bases += aln_len
            total_matches += int(best.score)
            contig_reports.append({
                "contig_id": c["id"],
                "length": len(seq),
                "score": float(best.score),
                "ref_start": int(t_coords[0][0]) if len(t_coords) else 0,
                "ref_end": int(t_coords[-1][1]) if len(t_coords) else 0,
                "identity": ident,
            })
        except Exception:
            continue

    genome_fraction = round(len(covered_positions) / len(ref_u), 4) if ref_u else 0.0
    mean_ident = round(total_matches / total_aligned_bases, 4) if total_aligned_bases else 0.0
    return {
        "reference_length": len(ref_u),
        "covered_bases": len(covered_positions),
        "genome_fraction": genome_fraction,
        "aligned_contigs": len(contig_reports),
        "mean_identity": min(1.0, mean_ident),
        "alignments": contig_reports,
    }
