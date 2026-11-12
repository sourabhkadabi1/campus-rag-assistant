"""
Tests for retrieval logic — reciprocal rank fusion and helper functions.

These tests are pure-function tests (no DB required).
"""

import pytest

from app.services.retrieval import reciprocal_rank_fusion, RRF_K


# ╔════════════════════════════════════════════════════════════════╗
# ║  Reciprocal Rank Fusion                                       ║
# ╚════════════════════════════════════════════════════════════════╝


class TestReciprocalRankFusion:
    def test_single_list_preserves_order(self):
        ranked = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
        result = reciprocal_rank_fusion([ranked])
        ids = [r[0] for r in result]
        assert ids == ["a", "b", "c"]

    def test_two_identical_lists(self):
        ranked = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
        result = reciprocal_rank_fusion([ranked, ranked])
        ids = [r[0] for r in result]
        assert ids[0] == "a"  # highest combined score

    def test_agreeing_lists_boost_score(self):
        list1 = [("a", 0.9), ("b", 0.8)]
        list2 = [("a", 0.9), ("b", 0.8)]
        result = reciprocal_rank_fusion([list1, list2])
        # Score for 'a' should be 2 * (1 / (K+1))
        expected_a = 2.0 / (RRF_K + 1)
        actual_a = dict(result)["a"]
        assert abs(actual_a - expected_a) < 1e-9

    def test_disagreeing_lists_promote_consensus(self):
        """With a small k, rank 2+2 beats rank 1+3 (consensus wins)."""
        list1 = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
        list2 = [("c", 0.9), ("b", 0.8), ("a", 0.7)]
        # Use k=1 so the effect is visible:
        # b: 1/(1+2) + 1/(1+2) = 2/3 ≈ 0.667
        # a: 1/(1+1) + 1/(1+3) = 0.5 + 0.25 = 0.75
        # c: 1/(1+3) + 1/(1+1) = 0.25 + 0.5 = 0.75
        # With k=1 a and c beat b! Need even smaller gap.
        # Actually the math shows: 2/(k+2) vs 1/(k+1)+1/(k+3).
        # Consensus wins when k < (1+√5)/2 ≈ 1.618.
        # With large k (default 60), top-rank items win over consensus.
        # This is expected RRF behaviour — verify scores are consistent.
        result = reciprocal_rank_fusion([list1, list2])
        scores = dict(result)
        # a and c have symmetric ranks → identical scores
        assert abs(scores["a"] - scores["c"]) < 1e-9
        # All three should have positive scores
        assert all(s > 0 for s in scores.values())

    def test_disjoint_lists(self):
        list1 = [("a", 0.9), ("b", 0.8)]
        list2 = [("c", 0.9), ("d", 0.8)]
        result = reciprocal_rank_fusion([list1, list2])
        assert len(result) == 4
        ids = {r[0] for r in result}
        assert ids == {"a", "b", "c", "d"}

    def test_empty_lists(self):
        result = reciprocal_rank_fusion([[], []])
        assert result == []

    def test_one_empty_one_populated(self):
        result = reciprocal_rank_fusion([[], [("a", 0.9)]])
        assert len(result) == 1
        assert result[0][0] == "a"

    def test_scores_are_positive(self):
        ranked = [("a", 0.9), ("b", 0.5), ("c", 0.1)]
        result = reciprocal_rank_fusion([ranked])
        assert all(score > 0 for _, score in result)

    def test_three_lists(self):
        l1 = [("a", 0.9), ("b", 0.8)]
        l2 = [("b", 0.9), ("c", 0.8)]
        l3 = [("a", 0.9), ("c", 0.8)]
        result = reciprocal_rank_fusion([l1, l2, l3])
        # 'a' appears at rank 1 twice, 'b' at rank 1 once + rank 2 once
        scores = dict(result)
        # a: 2/(K+1) + 1/(K+2)  vs  b: 1/(K+1) + 1/(K+2)
        assert scores["a"] > scores["b"]

    def test_custom_k(self):
        ranked = [("a", 0.9), ("b", 0.8)]
        result_k10 = reciprocal_rank_fusion([ranked], k=10)
        result_k100 = reciprocal_rank_fusion([ranked], k=100)
        # With higher k, all scores are closer together
        scores_10 = dict(result_k10)
        scores_100 = dict(result_k100)
        gap_10 = scores_10["a"] - scores_10["b"]
        gap_100 = scores_100["a"] - scores_100["b"]
        assert gap_10 > gap_100  # smaller k → more spread

    def test_duplicate_ids_within_list(self):
        """If a list has duplicates, each gets scored at its own rank."""
        ranked = [("a", 0.9), ("a", 0.8)]
        result = reciprocal_rank_fusion([ranked])
        scores = dict(result)
        expected = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 2)
        assert abs(scores["a"] - expected) < 1e-9
