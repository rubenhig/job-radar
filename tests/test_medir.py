from job_radar.medir import Caso, acierto, dejando_uno_fuera, kappa, mejor_umbral


def caso(nota, top):
    return Caso(1, "x", top, None, nota, False, "", "", None)


def test_separacion_perfecta():
    cs = [caso(n, True) for n in (80, 85, 90)] + [caso(n, False) for n in (10, 20, 40)]
    u = mejor_umbral(cs)
    assert 40 < u <= 80 and acierto(cs, u) == 1.0 and kappa(cs, u) == 1.0
    assert dejando_uno_fuera(cs) == 1.0


def test_kappa_descuenta_el_azar():
    # Siempre "top" con 80 % de tops: 80 % de acuerdo, pero κ = 0.
    cs = [caso(90, True)] * 8 + [caso(90, False)] * 2
    assert acierto(cs, 50) == 0.8 and kappa(cs, 50) == 0.0
