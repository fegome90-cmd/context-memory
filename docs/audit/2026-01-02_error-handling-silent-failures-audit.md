# 🔧 Auditoría 2: Manejo de Errores y Failures Silenciosos

**Fecha**: 2026-01-02
**Componente**: Todo el plugin
**Estado**: ⚠️ Problemas de debuggeabilidad encontrados
**Severidad**: 🟡 Media (afecta debuggeabilidad, no funcionalidad)

---

## Resumen Ejecutivo

El plugin usa **fallas silenciosas extensivamente** para no interrumpir el trabajo del usuario. Esto es correcto para un hook de sistema, pero **perdebuggeable** cuando hay problemas.

`★ Insight ─────────────────────────────────────`
- **Diseño intencional**: Silencio ante errores para no bloquear al usuario
- **Problema**: Sin logs, imposible diagnosticar problemas en producción
- **Recomendación**: Agregar modo debug/verbose con logging opcional
`─────────────────────────────────────────────────`

---

## Phase 1: Root Cause Investigation ✅

### 1.1 Mapeo de Manejo de Errores

| Archivo | Líneas | `except: pass` | `except: return` | Total |
|---------|--------|----------------|------------------|-------|
| `cm_track_operation.py` | 133 | 2 | 3 | **5** |
| `storage_jsonl.py` | 148 | 4 | 0 | **4** |
| `repo.py` | ~180 | 2 | 0 | **2** |
| `paths.py` | 132 | 0 | 1 | **1** |
| `parser.py` | ~130 | 0 | 0 | **0** |
| **TOTAL** | - | **8** | **4** | **12** |

### 1.2 Distribución por Severidad

| Tipo | Count | % | Ejemplo |
|------|-------|---|---------|
| **Debug log falla** | 1 | 8% | Línea 37-38 |
| **JSON inválido** | 1 | 8% | Línea 43-45 |
| **Path inválido** | 2 | 17% | Líneas 91-92, 118-119 |
| **Storage falla** | 1 | 8% | Líneas 126-128 |
| **fcntl no disponible** | 4 | 33% | storage_jsonl.py |
| **Git falla** | 2 | 17% | repo.py |
| **Desconocido** | 1 | 8% | línea 38 |

---

## Phase 2: Análisis Detallado ✅

### 2.1 Errores Silenciosos por Archivo

#### 2.1.1 `cm_track_operation.py` (Hook Principal)

```python
# Línea 37-38: Debug log
try:
    with open("/tmp/cm_hook_debug.log", "a") as f:
        f.write(f"[{os.times()[4]}] cm_track_operation.py called\n")
except:
    pass  # ❌ Silencia TODAS las excepciones

# Línea 43-45: JSON inválido
try:
    hook_input = json.load(sys.stdin)
except json.JSONDecodeError:
    return  # ✅ Correcto - input malformado

# Línea 91-92: Path inválido
try:
    rel_path = get_relative_path(file_path, repo_info.root)
except (ValueError, TypeError):
    return  # ✅ Correcto - path malicioso

# Línea 118-119: Event inválido
try:
    event = ContextEvent(...)
except (ValueError, TypeError):
    return  # ✅ Correcto - datos inválidos

# Línea 126-128: Storage falla
try:
    storage.append(event)
except (OSError, IOError):
    pass  # ⚠️ PROBLEMA - Perdió datos sin aviso
```

**Análisis**:

| # | Línea | ¿Correcto? | Razón |
|---|-------|------------|-------|
| 1 | 37-38 | ❌ NO | `except:` es muy amplio |
| 2 | 43-45 | ✅ Sí | JSON malformado es input inválido |
| 3 | 91-92 | ✅ Sí | Path inválido debe ser silenciado |
| 4 | 118-119 | ✅ Sí | Event inválido es data corruption |
| 5 | 126-128 | ⚠️ PARCIAL | Debería loggear al menos |

**🔴 PROBLEMA CRÍTICO**: Línea 37-38

```python
except:
    pass  # Silencia TODO: AttributeError, OSError, PermissionError, etc.
```

**Impacto**: Si hay un problema con el debug log, nunca lo sabremos.

**Mejora**:
```python
except (OSError, IOError, PermissionError):
    pass  # Específico y documentado
```

#### 2.1.2 `storage_jsonl.py` (Persistencia)

```python
# Líneas 56-61: fcntl no disponible (Windows)
try:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
except (AttributeError, OSError):
    pass  # ✅ Documentado - Windows no soporta fcntl

# Líneas 69-72: Release lock
try:
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
except (AttributeError, OSError):
    pass  # ✅ Correcto - si acquire falló, release también

# Líneas 89-92: append_many lock
try:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
except (AttributeError, OSError):
    pass  # ✅ Correcto - consistente

# Líneas 99-102: append_many unlock
try:
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
except (AttributeError, OSError):
    pass  # ✅ Correcto - consistente
```

**Análisis**: ✅ **Correcto** - está documentado que Windows no tiene fcntl.

**🟡 PERO**: No hay logs sobre locks fallidos, incluso en modo debug.

#### 2.1.3 `repo.py` (Detección de Repo)

```python
# Líneas 79-90: Git remote command
try:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=5  # ✅ Timeout presente
    )
    remote_url = result.stdout.strip()
except (FileNotFoundError, subprocess.TimeoutExpired):
    pass  # ⚠️ Silencia "git not found" y timeouts

# Líneas 145-156: Git branch command
try:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=5
    )
    current_branch = result.stdout.strip()
except (FileNotFoundError, subprocess.TimeoutExpired):
    pass  # ⚠️ Silencia "git not found" y timeouts
```

**Análisis**:

**Escenario**: Usuario NO tiene git instalado

```
1. detect_repo() → falla silenciosamente
2. cm_track_operation.py:84 → repo_info = None
3. cm_track_operation.py:86 → return (todo el hook se desactiva)
4. Usuario nunca sabe por qué no funciona
```

**Problema**: ❌ **Sin mensaje de error** - el usuario piensa que el plugin funciona.

**Mejora sugerida**:
```python
except FileNotFoundError:
    # Git no está instalado - loggear warning una vez
    _log_once("warning", "Git not found - context-memory disabled")
    pass
```

---

## Phase 3: Análisis de Impacto ✅

### 3.1 Escenarios de Fallo

| Escenario | Comportamiento Actual | Impacto en Usuario | Severidad |
|-----------|----------------------|-------------------|-----------|
| **Git no instalado** | Hook desactivado silenciosamente | No hay tracking, sin aviso | 🔴 Alta |
| **Permission denied en `/tmp`** | Debug log falla silenciosamente | Sin debug | 🟡 Media |
| **Disk full** | `OSError` silenciado en storage | Pierde datos | 🔴 Alta |
| **JSON malformado** | `return` temprano | Input inválido rechazado | 🟢 Baja |
| **Path traversal** | `return` temprano | Ataque prevenido | 🟢 Bajo |

### 3.2 Matriz de Debuggeabilidad

| Componente | Logs? | Errors? | Warnings? | Debuggable? |
|------------|-------|---------|-----------|-------------|
| `cm_track_operation.py` | ❌ No | ❌ No | ❌ No | ❌ **No** |
| `storage_jsonl.py` | ❌ No | ❌ No | ❌ No | ❌ **No** |
| `repo.py` | ❌ No | ❌ No | ❌ No | ❌ **No** |
| `paths.py` | ❌ No | ✅ ValueError | ❌ No | ⚠️ **Parcial** |
| `parser.py` | ✅ Sí | ✅ Sí | ⚠️ Limitado | ✅ **Sí** |

**Conclusión**: ❌ **El plugin no es debuggable en producción**.

---

## Phase 4: Recomendaciones ✅

### 4.1 Modo Verboso (IMPLEMENTAR)

```python
# cm_track_operation.py
import logging
import os

# Configurar logging
DEBUG = os.environ.get("CM_DEBUG", "0") == "1"
logger = logging.getLogger(__name__)

if DEBUG:
    logging.basicConfig(
        level=logging.DEBUG,
        filename="/tmp/cm_hook_debug.log",
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def main():
    if DEBUG:
        logger.debug("Hook called")

    # ... resto del código ...

    # Detect repo
    repo_info = detect_repo()
    if not repo_info:
        if DEBUG:
            logger.warning("Not in a git repo - hook disabled")
        return

    # ... storage ...
    except (OSError, IOError) as e:
        if DEBUG:
            logger.error(f"Storage failed: {e}")
        # Luego silenciar
        pass
```

### 4.2 Health Check Command

```python
# scripts/cm_health_check.py
#!/usr/bin/env python3
"""
Health check for context-memory plugin.

Checks:
- Git availability
- Write permissions
- Disk space
- Lock file availability
"""
import sys
import subprocess
from pathlib import Path

def check_git():
    """Check if git is available."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        print("✅ Git is available")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ Git not found - context-memory requires git")
        return False

def check_write_permissions():
    """Check if we can write to .claude/context_memory."""
    try:
        test_dir = Path(".claude/context_memory/sessions")
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        print("✅ Write permissions OK")
        return True
    except OSError as e:
        print(f"❌ Write permissions failed: {e}")
        return False

def check_disk_space():
    """Check if there's enough disk space (>100MB)."""
    import shutil
    stat = shutil.disk_usage(".")
    free_mb = stat.free / (1024 * 1024)
    if free_mb > 100:
        print(f"✅ Disk space OK ({free_mb:.0f}MB free)")
        return True
    else:
        print(f"⚠️  Low disk space ({free_mb:.0f}MB free)")
        return False

def main():
    """Run all health checks."""
    print("Context-Memory Health Check")
    print("=" * 40)

    checks = [
        check_git(),
        check_write_permissions(),
        check_disk_space(),
    ]

    print("=" * 40)
    if all(checks):
        print("✅ All checks passed")
        sys.exit(0)
    else:
        print("❌ Some checks failed - context-memory may not work")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### 4.3 Telemetry de Errores

```python
# Agregar a storage_jsonl.py
class JSONLStorage:
    def __init__(self, path: Path):
        self.path = path
        self.error_count = 0  # Contador de errores
        self.last_error = None

    def append(self, event: ContextEvent) -> None:
        try:
            # ... existing code ...
        except (OSError, IOError) as e:
            self.error_count += 1
            self.last_error = str(e)
            raise  # Re-raise para que caller decida

# En cm_track_operation.py
except (OSError, IOError) as e:
    if storage.error_count > 10:
        # Demasiados errores - reportar
        print(f"⚠️  Context-Memory: {storage.error_count} write failures")
    pass
```

---

## 📊 Resumen de Hallazgos

### 🔴 CRÍTICO

| # | Issue | Ubicación | Impacto |
|---|-------|-----------|---------|
| 1 | **Git no instalado = sin aviso** | `repo.py:79-90, 145-156` | Usuario no sabe por qué no funciona |
| 2 | **Disk full = pérdida de datos** | `storage_jsonl.py:126-128` | Eventos perdidos sin evidencia |

### 🟡 MEDIO

| # | Issue | Ubicación | Impacto |
|---|-------|-----------|---------|
| 1 | **Bare except** | `cm_track_operation.py:37` | Oculta otros bugs |
| 2 | **Sin logs de errores** | Todo el plugin | No debuggeable |
| 3 | **fcntl no disponible** | `storage_jsonl.py` | No hay warning para Windows |

### 🟢 BAJO

| # | Issue | Ubicación | Impacto |
|---|-------|-----------|---------|
| 1 | **Timeout de git** | `repo.py:79` | Puede ser muy corto |
| 2 | **Sin health check** | N/A | Difícil diagnosticar |

---

## ✅ Conclusiones

### Fortalezas

1. **Non-blocking**: El hook nunca interrumpe el trabajo del usuario
2. **Tolerant parsing**: Parser salta líneas inválidas sin crash
3. **Graceful degradation**: Funciona sin git (aunque limitado)

### Debilidades

1. **No debuggeable**: Sin logs, imposible diagnosticar problemas
2. **No health checks**: No hay forma de verificar configuración
3. **Silent failures**: Errores críticos (git, disk) son silenciados

### Recomendaciones

#### Inmediato

1. ✅ **Implementar modo DEBUG** con variable de entorno
2. ✅ **Crear comando `/cm-health`** para diagnóstico
3. ✅ **Reemplazar `except:` con excepciones específicas**

#### Corto Plazo

1. **Agregar telemetry** básica (contador de errores)
2. **Documentar requisitos** (git, permisos) en README
3. **Agregar warning** cuando git no está instalado

#### Largo Plazo

1. **Sistema de logging** configurable
2. **Métricas** de uso y errores
3. **Dashboard** de diagnóstico

---

## Sources

- [Python Anti-Patterns: Bare Except](https://docs.python.org/3/howto/doanddont.html#except)
- [Logging Best Practices](https://docs.python.org/3/howto/logging.html)
- [Graceful Degradation Patterns](https://en.wikipedia.org/wiki/Fail-safe_systems)

---

**Fin de Auditoría 2** 📌
