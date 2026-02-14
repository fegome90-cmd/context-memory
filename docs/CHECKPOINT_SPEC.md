# Checkpoint Specification

## Format (2 líneas máximo)

```
CHK: <objective> | DONE: <n> | NEXT: <n>
FOCUS: <dir1>,<dir2> | EVID: <PASS/FAIL/n-a>
```

## Hard Caps

- **Línea 1**: máximo 280 caracteres
- **Línea 2**: máximo 280 caracteres
- **Total**: 2 líneas máximo

## Calculation Rules

### DONE (work signal)
- Si hubo Write/Edit significativo: `DONE: edited` (n=1)
- Si solo reads: `DONE: reviewed` (n=1)
- Si no hay señal: `DONE: n/a`

### NEXT (resume point)
- Basado en último evento o prompt
- Si no hay señal: `NEXT: resume in <FOCUS>`
- Formato: `NEXT: resume in src/` o similar

### FOCUS (top dirs)
- Top 1-3 directorios por score:
  - Write/Edit pesan más que Read
  - Recencia (más reciente = mayor peso)
- Formato: `FOCUS: dir1,dir2` (sin paths completos)

### EVID (evidence/gates)
- Si context-memory conoce gates/pass/fail: usar ese valor
- Si no hay señal: `EVID: n-a` (no alucinar)

## Fallback Rules

Si no hay señal confiable:
- `CHK: n/a | DONE: n/a | NEXT: n/a`
- `FOCUS: n/a | EVID: n-a`

## Sanitization

- No paths absolutos
- No tabs, solo spaces
- No newlines extra
- Solo caracteres ASCII imprimibles

## Atomic Write

 checkpoint.tmp → rename → checkpoint.txt
