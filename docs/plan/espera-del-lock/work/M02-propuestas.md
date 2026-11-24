# M02 — Propuestas para documentos compartidos

## `docs/tests/state-backends.md`

En "UT-ST-08 — Reintento del lock", **Tabla: Casos de UT-ST-08**: quitar el marcador `[pendiente]` de los casos .01 a .09. Los nueve están implementados en `tests/test_state.py` (`RunLockRetryTest`, `test_ut_st_08_01` a `test_ut_st_08_09`) y pasan solos y en la suite completa. El resto del texto de cada caso no cambia.

## Otros documentos compartidos

Ninguna propuesta para `MASTER-PLAN.md`, `INTEGRACION.md`, `REGLAS.md`, `TRAZABILIDAD.md`, `DECISIONES.md`, `REGISTRO.md`, `evidence/`, `docs/changes/espera-del-lock.md` ni `docs/prd/`.

## Nota para M03

- Firma: `RunLock(home, retry: LockConfig | None = None, *, sleep=time.sleep)`. Sin `retry` (como debe construirlo el chequeo `lock` de `doctor`) hace un solo intento y da el `hint` de "Sin reintentos"; con `config.lock` aplica los reintentos.
- `state.py` importa `LockConfig` solo para anotaciones (`TYPE_CHECKING`): no hay dependencia de importación de `state` hacia `config`.
- Constante pública nueva: `mailquery.state.LOCK_PAUSE_CAP_MS = 5000`.
