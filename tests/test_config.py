from sca.config import load_config


def test_config_yaml_loads_and_validates():
    cfg = load_config()
    assert cfg.seed == 42
    assert cfg.simulation.n_sims == 10_000
    assert len(cfg.simulation.lead_time_weeks) == len(cfg.simulation.lead_time_probs)
    assert abs(sum(cfg.simulation.lead_time_probs) - 1.0) < 1e-9
    assert 0 < cfg.risk.test_fraction < 0.5
