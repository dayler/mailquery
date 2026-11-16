## 9. IDs retirados

Estos IDs ya no tienen test y no se reutilizan:

| ID | Qué cubría | Lo sustituye |
|---|---|---|
| UT-CLI-01, UT-CLI-02, UT-CLI-03 | `--version`: formato, sin efectos y combinaciones | UT-PL-03 |
| UT-CLI-06 | Ayudas | UT-ATC-09 |
| UT-CLI-07 | Formato del uid de `show` (uid entero) | UT-ATC-02, UT-ATC-03, UT-UID-02 |
| UT-ST-02.03, .04, .05 y .07; UT-ST-03 | Validación de uids enteros y hexadecimales en `state.json` | UT-ST-06, UT-ST-07 |
| UT-ST-04.02 | `new` con estado corrupto | — |
| TC-05.04, .05 y .06 | Paridad de forma de `mailboxes`, error y `doctor` | TC-05.01 y TC-05.03 |
| TC-06.04 | `requires-python` ≥ 3.11 | — |
| TC-07.05 | Exits en las recetas | — |
| DOC-05.05 | Recorrido de las siete ayudas | DOC-05.03 |
| UT-ATC-10.03 | Un plugin `attachments: "remote"` no podía materializar adjuntos (`unsupported`) | UT-RMT-01, UT-RMT-02, UT-RMT-03 |
