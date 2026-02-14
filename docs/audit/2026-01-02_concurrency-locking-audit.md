# # 🔒 Auditoría 3: Concurrencia y File Locking

**Fecha**: 2026-01-02
**Componente**: `infrastructure/storage_jsonl.py`
**Estado**: ⚠️ Implementación correcta pero con limitaciones
**Severidad**: 🟡 Media (afecta escenarios de alta concurrencia)

---

## Resumen Ejecutivo

El plugin usa `fcntl.flock()` para locking en Unix, pero **no hay locking en Windows**. El diseño es correcto para el caso de uso (append-only, single writer), pero tiene limitaciones en escenarios multi-proceso.

`★ Insight ─────────────────────────────────────`
- **fcntl es correcto para append-only**: Evita corridas de escritura
- **Windows sin locks**: Race condition posible en multi-proceso
- **No hay starvation protection**: Locks pueden acumularse
`─────────────────────────────────────────────────`

---

## Phase 1: Root Cause Investigation ✅

### 1.1 Implementación de Locking

```python
# storage_jsonl.py:40-73
def append(self, event: ContextEvent) -> None:
    """
    Append a single event to the JSONL file.

    Thread-safe via file locking (Unix only).
    On Windows, writes without lock (best-effort).
    """
    self.path.parent.mkdir(parents=True, exist_ok=True)

    with open(self.path, "a") as f:
        # Acquire exclusive lock
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # ← LOCK
        except (AttributeError, OSError):
            pass  # ← Windows: NO LOCK

        try:
            f.write(serialize_event(event) + "\n")
            f.flush()  # ← FORCE WRITE
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # ← UNLOCK
            except (AttributeError, OSError):
                pass  # ← Windows: NO UNLOCK NEEDED
```

**Análisis**:

| Aspecto | Unix | Windows |
|---------|------|---------|
| **Lock acquire** | ✅ `fcntl.flock(LOCK_EX)` | ❌ Ninguno |
| **Lock release** | ✅ `fcntl.flock(LOCK_UN)` | ❌ Ninguno |
| **Flush** | ✅ `f.flush()` | ✅ `f.flush()` |
| **Race condition** | ✅ Protegido | ❌ **VULNERABLE** |

### 1.2 Escenarios de Condiciones de Carrera

#### Escenario 1: Multi-Proceso en Unix (PROTEGIDO)

```
Time  Process A                    Process B
───── ──────────────────────────── ────────────────────────────
T1    fcntl(LOCK_EX) → espera
T2    ✅ Lock adquirido
T3                                fcntl(LOCK_EX) → bloqueado
T4    write + flush
T5    fcntl(LOCK_UN)
T6                                ✅ Lock adquirido
T7                                write + flush
T8                                fcntl(LOCK_UN)
```

**Resultado**: ✅ **Sin race condition** - escrituras serializadas.

#### Escenario 2: Multi-Proceso en Windows (VULNERABLE)

```
Time  Process A                    Process B
───── ──────────────────────────── ────────────────────────────
T1    open("a")
T2                                open("a")
T3    write("event1\n")
T4                                write("event2\n")  ← CORRUPTIÓN
T5    flush()
T6                                flush()
```

**Resultado**: ❌ **Race condition** - posible intercalación de bytes.

**Ejemplo de corrupción**:

```jsonl
{"operation":"read","file_path":"src/app1.py"}
{"operation":"read{"operation":"write","file_path":"src/app2.py"}
```

---

## Phase 2: Análisis de fcntl Behavior ✅

### 2.1 Propiedades de fcntl.flock()

| Propiedad | Valor | Implicación |
|-----------|-------|-------------|
| **Mecanismo** | Advisory lock | No previene acceso directo |
| **Alcance** | Process-local | No heredado por child processes |
| **Blocking** | Sí (por defecto) | Puede causar deadlocks |
| **Release on close** | Sí | Garantiza limpieza |
| **Cross-platform** | Unix only | No disponible en Windows |

### 2.2 Advisory Locking (⚠️ LIMITACIÓN)

**Advisory** significa: "Los procesos que cooperan respetan el lock; los que no, lo ignoran."

**Escenario problemático**:

```bash
# Proceso 1: Hook de context-memory (respeta lock)
fcntl.flock(fd, LOCK_EX)

# Proceso 2: Editor de texto (no sabe del lock)
vim current.jsonl  # ← Escribe directamente

# Resultado: Ambos escriben al mismo tiempo
```

**Conclusión**: `fcntl` protege contra **el mismo plugin** en multi-proceso, pero **NO contra procesos externos**.

### 2.3 Blocking vs Non-Blocking

**Actual**: `fcntl.flock(fd, LOCK_EX)` → bloqueante (infinito)

**Problema**: Si un proceso muere con el lock, otros esperan para siempre.

**Mejora**: Usar `LOCK_EX | LOCK_NB`

```python
try:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    # Lock no disponible - decidir qué hacer
    raise RuntimeError("Could not acquire lock - file is busy")
```

**Pero**: Para append-only, blocking es correcto (esperar es lo que queremos).

---

## Phase 3: Escenarios Reales ✅

### 3.1 Multi-Proceso: Claude Code + Hook

**Configuración típica**:
- 1 proceso principal de Claude Code
- N hooks ejecutándose concurrentemente (Read/Write/Edit tools en paralelo)
- 1 archivo `current.jsonl` compartido

**Pregunta**: ¿Puede haber múltiples hooks escribiendo al mismo tiempo?

**Respuesta**: ✅ **SÍ, POSIBLE**

```python
# Claude Code puede ejecutar múltiples tools en paralelo
# Hook 1: Read tool → PostToolUse → append("read event")
# Hook 2: Write tool → PostToolUse → append("write event")
# Ambos llaman a storage.append() simultáneamente
```

**Con fcntl**: ✅ Protegido (espera turno)
**Sin fcntl (Windows)**: ❌ Corrupción posible

### 3.2 Multi-Hilo: No Aplica

```bash
$ grep -r "threading" context-memory/
# (No results)
```

**Conclusión**: El plugin no usa threads, solo multi-proceso.

### 3.3 Deadlocks: Posibles

#### Escenario 1: Lock Acquisition

```python
# Proceso A
fcntl.flock(fd, LOCK_EX)  # Adquiere lock

# Proceso A: CRASH (mata el proceso)
# Lock NUNCA se libera

# Proceso B
fcntl.flock(fd, LOCK_EX)  # ← BLOQUEADO PARA SIEMPRE
```

**Protección**: ✅ **Release on close**

Del man page de flock(2):
> "Locks are released when the file descriptor is closed."

**Pero**: Si el archivo es mantenido abierto, el lock persiste.

#### Escenario 2: Multiple Locks (NO IMPLEMENTADO)

El plugin solo tiene 1 lock por archivo, así que no hay deadlocks por múltiples locks.

---

## Phase 4: Testing de Condiciones de Carrera ✅

### 4.1 Tests Existentes

```bash
$ pytest tests/test_infra_storage_jsonl.py -v
```

**¿Hay tests de concurrencia?** ❌ NO.

### 4.2 Test Sugerido

```python
# test_concurrency.py
import concurrent.futures
import time

def test_concurrent_append(storage, events):
    """Test that concurrent appends don't corrupt data."""
    def append_event(event):
        storage.append(event)

    # Lanzar 10 procesos escribiendo 100 eventos cada uno
    with concurrent.futures.ProcessPoolExecutor(max_workers=10) as executor:
        futures = []
        for event in events:
            futures.append(executor.submit(append_event, event))

        concurrent.futures.wait(futures)

    # Verificar: todos los eventos están ahí
    stored = list(storage.read_all())
    assert len(stored) == len(events)

    # Verificar: no hay corrupción (todos JSON válidos)
    for event in stored:
        assert event.operation in ["read", "write", "edit"]
```

### 4.3 Test de Windows

```python
# test_windows_locking.py
import platform

@pytest.mark.skipif(platform.system() != "Windows", reason="Windows only")
def test_windows_no_locking(tmp_path):
    """Test that Windows writes without lock (best-effort)."""
    from infrastructure.storage_jsonl import JSONLStorage

    storage = JSONLStorage(tmp_path / "test.jsonl")

    # Simular escritura concurrente sin locks
    events = [create_test_event(i) for i in range(100)]

    def write_events(evts):
        for evt in evts:
            # Simular ausencia de fcntl
            with open(storage.path, "a") as f:
                f.write(serialize_event(evt) + "\n")
                f.flush()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(write_events, events[i::4]) for i in range(4)]
        concurrent.futures.wait(futures)

    # Verificar integridad (puede fallar en Windows)
    stored = list(storage.read_all())
    assert len(stored) == 100  # ← Puede fallar
```

---

## 📊 Resumen de Hallazgos

### 🔴 CRÍTICO

| # | Issue | Ubicación | Impacto |
|---|-------|-----------|---------|
| 1 | **Windows sin locks** | `storage_jsonl.py:59-60` | Race condition en multi-proceso |
| 2 | **Sin tests de concurrencia** | `tests/` | No hay verificación |

### 🟡 MEDIO

| # | Issue | Ubicación | Impacto |
|---|-------|-----------|---------|
| 1 | **Advisory locking** | `storage_jsonl.py:57` | No previene acceso externo |
| 2 | **Blocking locks** | `storage_jsonl.py:57` | Puede bloquear indefinidamente |
| 3 | **Sin timeout** | N/A | No hay mecanismo de timeout |

### 🟢 BAJO

| # | Issue | Ubicación | Impacto |
|---|-------|-----------|---------|
| 1 | **No priority** | N/A | Todos los locks son iguales |
| 2 | **No lock order** | N/A | Solo 1 lock, no riesgo de deadlock |

---

## ✅ Conclusiones

### Fortalezas

1. **Unix locking**: `fcntl` es correcto para el caso de uso
2. **Flush after write**: `f.flush()` garantiza escritura
3. **Release on close**: Cleanup automático de locks
4. **Single writer**: Arquitectura append-only reduce riesgos

### Debilidades

1. **Windows sin locks**: Race condition real en multi-proceso
2. **Advisory locking**: No previene accesos externos
3. **Sin tests**: No hay verificación de concurrencia
4. **Sin timeout**: Lock bloqueante puede causar hangs

### Recomendaciones

#### Inmediato

1. **Documentar limitación de Windows** en README
2. **Agregar test de concurrencia** básico
3. **Agregar warning** en Windows

#### Corto Plazo

1. **Implementar locking para Windows** usando `msvcrt.locking`
2. **Agregar timeout** a locks (usando `fcntl.LOCK_NB` + retry)
3. **Monitorear** lock acquisitions para detectar contención

#### Largo Plazo

1. **Considerar sqlite** como backend (tiene locking robusto)
2. **Implementar queue** para escrituras (serializar explícitamente)
3. **Agregar métricas** de lock wait time

---

## Implementación Sugerida: Windows Locking

```python
# storage_jsonl.py
import platform
import sys

if platform.system() == "Windows":
    import msvcrt
    HAS_LOCKING = True
else:
    import fcntl
    HAS_LOCKING = True

class JSONLStorage:
    def _acquire_lock(self, f):
        """Acquire exclusive lock (cross-platform)."""
        if platform.system() == "Windows":
            # Windows: Use msvcrt.locking
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            except IOError:
                raise IOError("Could not acquire lock - file is busy")
        else:
            # Unix: Use fcntl
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise IOError("Could not acquire lock - file is busy")

    def _release_lock(self, f):
        """Release exclusive lock (cross-platform)."""
        if platform.system() == "Windows":
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

---

## Sources

- [flock(2) man page](https://man7.org/linux/man-pages/man2/flock.2.html)
- [msvcrt.locking documentation](https://docs.microsoft.com/en-us/cpp/c-runtime-library/reference/locking)
- [Python fcntl documentation](https://docs.python.org/3/library/fcntl.html)
- [Advisory vs Mandatory Locking](https://en.wikipedia.org/wiki/File_locking#Advisory_vs_mandatory_locks)

---

**Fin de Auditoría 3** 📌
