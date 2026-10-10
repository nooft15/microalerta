"""Pruebas de la lógica científica (métricas, semáforo, control, autocuidado)."""
import pytest

from microalerta import science


def test_concentration_and_deposition():
    m = science.compute_metrics(63, 40, 4.0, exposure_hours=24)
    assert m["conc_p_ml"] == pytest.approx(63 / 40, abs=1e-3)
    assert m["depo_p_cm2"] == pytest.approx(63 / 4.0, abs=1e-2)
    # 63 p / 4 cm² = 15.75 p/cm² -> *1e4 = 157500 p/m² ; /1 día = 157500
    assert m["depo_p_m2_day"] == pytest.approx(157500.0, rel=1e-3)
    assert m["exposure_hours"] == 24


def test_empty_blank_is_zero():
    m = science.compute_metrics(0)
    assert m["n_observed"] == 0
    assert m["conc_p_ml"] == 0


def test_semaphore_levels():
    assert science.semaphore(0.2)["level"] == 0
    assert science.semaphore(0.5)["level"] == 1   # límite: 0.5 -> moderada
    assert science.semaphore(1.9)["level"] == 1
    assert science.semaphore(2.0)["level"] == 2
    assert science.semaphore(4.9)["level"] == 2
    assert science.semaphore(5.0)["level"] == 3
    assert science.semaphore(12.0)["level"] == 3


def test_semaphore_scale_complete():
    """La escala trae los 4 niveles con color, rango y recomendaciones."""
    scale = science.semaphore_scale()
    assert len(scale) == 4
    for i, lv in enumerate(scale):
        assert lv["level"] == i
        assert lv["label"] and lv["color"] and lv["range"]
        assert isinstance(lv["recommendations"], list) and lv["recommendations"]
        # sin emojis
        assert not [ch for ch in str(lv["label"]) + str(lv["range"]) if ord(ch) >= 0x1F000]
    # los colores de la escala coinciden con semaphore() en cada nivel
    assert science.semaphore(0.2)["color"] == scale[0]["color"]
    assert science.semaphore(3.0)["color"] == scale[2]["color"]
    assert science.semaphore(9.0)["color"] == scale[3]["color"]


def test_blank_control_qc():
    ok = science.blank_qc(0)
    assert ok["ok"] is True
    ok2 = science.blank_qc(2)
    assert ok2["ok"] is True  # tolerancia = 2
    bad = science.blank_qc(5)
    assert bad["ok"] is False
    assert "contaminación" in bad["detail"].lower()


def test_replicates_group():
    group = [
        {"sample_type": "muestra", "n_observed": 40},
        {"sample_type": "replica", "n_observed": 38},
        {"sample_type": "blanco", "n_observed": 1},
    ]
    notes = science.replicates_qc(group)
    assert notes == []  # cumple: 3 platos + blanco válido

    notes2 = science.replicates_qc([
        {"sample_type": "muestra", "n_observed": 40},
    ])
    joined = " ".join(notes2).lower()
    assert "más de" in joined or "no se registró" in joined


def test_self_care_reactions():
    rec = science.self_care(conc=6.0, hum=15, wind_kmh=45, temp=33)
    text = " ".join(r["title"] + r["detail"] for r in rec).lower()
    assert "n95" in text            # nivel muy alto
    assert "viento" in text         # ráfagas > 40
    assert "seco" in text           # humedad < 20
    assert "calor" in text          # temp >= 30

    rec2 = science.self_care(conc=0.1, hum=60, wind_kmh=10, temp=15)
    assert any("saludable" in r["detail"].lower() or "limpio" in r["detail"].lower()
               for r in rec2)
    assert len(rec2) == 1  # sin modificadores


def test_self_care_ordering_and_priority():
    rec = science.self_care(conc=6.0, wind_kmh=50)
    prios = [r["priority"] for r in rec]
    assert prios == sorted(prios, reverse=True)
    assert len(rec) >= 2


# ── Índice de exposición tipo UV ────────────────────────────────────────────
def test_plastic_index_bands():
    assert science.plastic_index(0.0)["index"] == 0
    assert science.plastic_index(0.02)["index"] == 0
    assert science.plastic_index(0.06)["index"] == 2
    assert science.plastic_index(0.5)["index"] == 4
    assert science.plastic_index(1.5)["index"] == 6
    assert science.plastic_index(3.0)["index"] == 7
    assert science.plastic_index(6.0)["index"] == 9
    assert science.plastic_index(8.0)["index"] == 9
    assert science.plastic_index(20.0)["index"] == science.INDEX_MAX
    top = science.plastic_index(50.0)
    assert top["index_label"].endswith("+")


def test_plastic_index_categories_and_colors():
    low = science.plastic_index(0.01)
    assert low["label"] == "Muy bajo"
    assert low["color"] == science.INDEX_COLORS[0]
    extreme = science.plastic_index(30.0)
    assert extreme["label"] == "Extremo"
    assert extreme["color"] == science.INDEX_COLORS[-1]
    mid = science.plastic_index(1.0)
    assert mid["label"] == "Moderado"


def test_no_emojis_in_science_output():
    """La interfaz no debe recibir emojis desde la lógica científica."""
    samples = [
        science.semaphore(6.0),
        science.plastic_index(6.0),
        *science.self_care(conc=6.0, wind_kmh=50, temp=32),
        *science.self_care(conc=0.2),
    ]
    for obj in samples:
        text = "".join(str(v) for v in obj.values() if isinstance(v, str))
        emoji_chars = [ch for ch in text if ord(ch) >= 0x1F000]
        assert not emoji_chars, f"emoji encontrado en: {text}"


def test_self_care_units_formatting():
    rec = science.self_care(conc=6.0, wind_kmh=50, temp=32,
                            units_pref={"wind": "mph", "temp": "F"})
    joined = " ".join(r["detail"] for r in rec)
    assert "mph" in joined      # viento formateado en millas por hora
    assert "°F" in joined       # temperatura formateada en Fahrenheit

    rec_si = science.self_care(conc=6.0, wind_kmh=50, temp=32)
    joined_si = " ".join(r["detail"] for r in rec_si)
    assert "km/h" in joined_si and "°C" in joined_si