from suth.scoring import friction_score
from suth.taxonomy import FailureHit


def test_objective_met_scores_lowest():
    assert friction_score(2, "objective_met", []) == 2.0


def test_penalty_added_per_hit_and_verdict():
    hits = [FailureHit("dead_click", 1, "x"), FailureHit("dead_click", 3, "y")]
    score = friction_score(4, "dead_click", hits)
    # 4 (frustration) + 2.0 + 2.0 (two dead_click hits) + 2.0 (dead_click verdict)
    assert score == 10.0


def test_same_transcript_produces_stable_score():
    hits = [FailureHit("label_ambiguity", 2, "x")]
    a = friction_score(3, "label_ambiguity", hits)
    b = friction_score(3, "label_ambiguity", hits)
    assert a == b


def test_worse_transcript_scores_higher():
    mild = friction_score(1, "dead_click", [FailureHit("dead_click", 1, "x")])
    severe = friction_score(1, "silent_failure", [FailureHit("dead_click", 1, "x")] * 3)
    assert severe > mild
