"""
ML Engine: Scikit-learn Machine Learning for De Bruijn Assembly & Metagenomics
=============================================================================
Provides data-driven statistical and machine learning methods for NGS de Bruijn graphs:
* Gaussian Mixture Models (GMM) to model error vs genomic k-mer coverage distributions
  and compute optimal Bayes decision boundaries for error pruning.
* Trinucleotide frequency (TNF) profiling and feature extraction for contig composition.
* Metagenomic contig binning using StandardScaler, PCA dimensionality reduction, and KMeans
  clustering (with automatic silhouette score optimization).
* Assembly anomaly / chimerism / contaminant detection via IsolationForest.
"""

from __future__ import annotations

import statistics
from collections import Counter

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler


def kmer_spectrum(kmers: list[str]) -> dict[int, int]:
    """Coverage histogram: {coverage_depth: number_of_distinct_kmers_at_that_depth}."""
    counts = Counter(kmers)
    spectrum = Counter(counts.values())
    return dict(sorted(spectrum.items()))


def coverage_summary(kmers: list[str]) -> dict:
    """Summary statistics for the k-mer coverage distribution."""
    counts = Counter(kmers)
    if not counts:
        return {}
    coverages = sorted(counts.values())
    return {
        "unique_kmers": len(counts),
        "total_kmers": len(kmers),
        "min_cov": coverages[0],
        "max_cov": coverages[-1],
        "mean_cov": round(statistics.mean(coverages), 2),
        "median_cov": statistics.median(coverages),
    }


def estimate_error_threshold(spectrum: dict[int, int]) -> int:
    """Heuristic coverage cutoff separating sequencing errors from real k-mers."""
    if len(spectrum) < 3:
        return 1
    coverages = sorted(spectrum.keys())
    counts = [spectrum[c] for c in coverages]
    for i in range(1, len(counts) - 1):
        if counts[i] <= counts[i - 1] and counts[i] < counts[i + 1]:
            return coverages[i]
    return 1


def fit_kmer_error_model(spectrum: dict[int, int]) -> tuple[int, dict]:
    """Fit a 2-component Gaussian Mixture Model (scikit-learn) on log k-mer counts.

    Separates sequencing error k-mers (peak near 1-2x) from genuine genomic
    k-mers (peak at sequencing depth). Calculates the Bayes decision cutoff
    where P(genomic) > P(error). Falls back gracefully to heuristic valley
    detection if data size is small."""
    if len(spectrum) < 4:
        c = estimate_error_threshold(spectrum)
        return c, {"method": "heuristic", "cutoff": c}
    coverages = np.array(sorted(spectrum.keys()))
    counts = np.array([spectrum[c] for c in coverages])
    if coverages[-1] < 4:
        c = estimate_error_threshold(spectrum)
        return c, {"method": "heuristic", "cutoff": c}

    sample_points = []
    for cov, count in zip(coverages, counts):
        sample_points.extend([cov] * min(count, 500))

    if len(sample_points) < 20:
        c = estimate_error_threshold(spectrum)
        return c, {"method": "heuristic", "cutoff": c}

    X = np.log1p(np.array(sample_points, dtype=float)).reshape(-1, 1)
    try:
        gmm = GaussianMixture(n_components=2, random_state=42, n_init=3)
        gmm.fit(X)
        means = np.expm1(gmm.means_).ravel()
        weights = gmm.weights_.ravel()
        idx = np.argsort(means)
        err_idx, gen_idx = idx[0], idx[1]
        err_mean, gen_mean = means[err_idx], means[gen_idx]

        if gen_mean < err_mean * 1.4:
            c = estimate_error_threshold(spectrum)
            return c, {"method": "heuristic (overlapping components)", "cutoff": c}

        test_covs = np.arange(1, int(gen_mean) + 2)
        test_X = np.log1p(test_covs).reshape(-1, 1)
        probs = gmm.predict_proba(test_X)
        gen_probs = probs[:, gen_idx]
        boundary_idx = np.where(gen_probs >= 0.5)[0]
        if len(boundary_idx) > 0:
            cutoff = int(test_covs[boundary_idx[0]])
        else:
            cutoff = max(1, int(round((err_mean + gen_mean) / 2)))

        stats = {
            "method": "scikit-learn GaussianMixture",
            "error_mean_cov": round(float(err_mean), 2),
            "genomic_mean_cov": round(float(gen_mean), 2),
            "cutoff": cutoff,
            "weights": [round(float(w), 3) for w in weights[idx]],
            "converged": bool(gmm.converged_),
        }
        return max(1, cutoff), stats
    except Exception:
        c = estimate_error_threshold(spectrum)
        return c, {"method": "heuristic (fallback)", "cutoff": c}


def extract_kmer_features(seq: str, k: int = 3) -> np.ndarray:
    """Extract normalized k-mer frequency vector for contig composition analysis."""
    seq = seq.upper()
    bases = "ACGT"
    all_kmers = [a + b + c for a in bases for b in bases for c in bases]
    kmer_idx = {km: i for i, km in enumerate(all_kmers)}
    vec = np.zeros(len(all_kmers), dtype=float)
    if len(seq) >= k:
        for i in range(len(seq) - k + 1):
            km = seq[i : i + k]
            if km in kmer_idx:
                vec[kmer_idx[km]] += 1
        total = np.sum(vec)
        if total > 0:
            vec /= total
    return vec


def bin_contigs(contigs: list[dict], n_clusters: int | None = None) -> tuple[list[dict], dict]:
    """Metagenomic contig binning, PCA, and anomaly detection with scikit-learn.

    Uses normalized trinucleotide frequencies, GC fraction, and coverage depth.
    Applies StandardScaler, PCA (2D coordinates), KMeans clustering (with
    silhouette optimization), and IsolationForest outlier detection."""
    n = len(contigs)
    if n < 2:
        for c in contigs:
            c.setdefault("bin_id", 1)
            c.setdefault("pca_x", 0.0)
            c.setdefault("pca_y", 0.0)
            c.setdefault("is_outlier", False)
        return contigs, {"n_bins": 1 if n == 1 else 0, "clusters": {}}

    feature_rows = []
    for c in contigs:
        km_feats = extract_kmer_features(c["sequence"], k=3)
        gc = c.get("gc_content", 0.0)
        cov = np.log1p(c.get("mean_coverage", 1.0))
        combined = np.hstack([km_feats, [gc * 5.0, cov]])
        feature_rows.append(combined)

    X = np.array(feature_rows)
    n_unique = len(np.unique(X, axis=0))
    if n_unique < 2:
        for c in contigs:
            c["bin_id"] = 1
            c["pca_x"] = 0.0
            c["pca_y"] = 0.0
            c["is_outlier"] = False
        return contigs, {
            "n_bins": 1,
            "pca_variance_ratio": [],
            "outlier_count": 0,
            "clusters": {
                "Bin 1": {
                    "contigs": n,
                    "total_bp": sum(c["length"] for c in contigs),
                    "mean_gc": round(float(np.mean([c["gc_content"] for c in contigs])), 3),
                    "mean_cov": round(float(np.mean([c["mean_coverage"] for c in contigs])), 1),
                }
            },
        }

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # PCA 2D projection
    n_comp = min(2, X_scaled.shape[0], X_scaled.shape[1])
    pca = PCA(n_components=n_comp, random_state=42)
    coords = pca.fit_transform(X_scaled)
    try:
        var_ratio = [round(float(v), 3) for v in pca.explained_variance_ratio_ if not np.isnan(v)]
    except Exception:
        var_ratio = []

    # KMeans clustering with silhouette selection
    if n_clusters is not None:
        k = max(1, min(n_clusters, n_unique))
    elif n >= 4 and n_unique >= 3:
        best_k, best_score = 2, -1.0
        max_test_k = min(5, n_unique, n - 1)
        for test_k in range(2, max_test_k + 1):
            km_test = KMeans(n_clusters=test_k, random_state=42, n_init="auto").fit(X_scaled)
            score = silhouette_score(X_scaled, km_test.labels_)
            if score > best_score:
                best_score = score
                best_k = test_k
        k = best_k
    else:
        k = 2 if n_unique >= 2 else 1

    kmeans = KMeans(n_clusters=k, random_state=42, n_init="auto").fit(X_scaled)
    labels = kmeans.labels_

    # Anomaly detection via IsolationForest
    outliers = np.ones(n, dtype=int)
    if n >= 4 and n_unique >= 3:
        try:
            iso = IsolationForest(contamination=0.1, random_state=42)
            outliers = iso.fit_predict(X_scaled)
        except Exception:
            pass

    for i, c in enumerate(contigs):
        c["bin_id"] = int(labels[i]) + 1
        c["pca_x"] = round(float(coords[i, 0]), 3) if coords.shape[1] >= 1 else 0.0
        c["pca_y"] = round(float(coords[i, 1]), 3) if coords.shape[1] >= 2 else 0.0
        c["is_outlier"] = bool(outliers[i] == -1)

    bin_counts = Counter(labels)
    clusters_info = {}
    for b_idx in sorted(bin_counts.keys()):
        b_id = int(b_idx) + 1
        bin_contigs_list = [c for c in contigs if c["bin_id"] == b_id]
        clusters_info[f"Bin {b_id}"] = {
            "contigs": len(bin_contigs_list),
            "total_bp": sum(c["length"] for c in bin_contigs_list),
            "mean_gc": round(float(np.mean([c["gc_content"] for c in bin_contigs_list])), 3),
            "mean_cov": round(float(np.mean([c["mean_coverage"] for c in bin_contigs_list])), 1),
        }

    summary = {
        "n_bins": k,
        "pca_variance_ratio": var_ratio,
        "outlier_count": int(np.sum(outliers == -1)),
        "clusters": clusters_info,
    }
    return contigs, summary
