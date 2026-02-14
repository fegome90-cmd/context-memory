# 🔒 Auditoría 1: Seguridad - Path Traversal y Validación

**Fecha**: 2026-01-02
**Componente**: `infrastructure/paths.py` y `cm_track_operation.py`
**Estado**: ✅ Seguro con implementación robusta
**Severidad**: 🟢 Baja (bien mitigado)

---

## Resumen Ejecutivo

El plugin `context-memory` implementa **validación de seguridad robusta** contra path traversal. Se encontraron múltiples capas de protección con tests adecuados.

`★ Insight ─────────────────────────────────────`
- **Defense in depth**: 3 capas de validación independientes
- **Fail-safe defaults**: Silencio ante input inválido en lugar de crash
- **Test coverage**: Tests específicos de seguridad presentes
`─────────────────────────────────────────────────`

---

## Phase 1: Root Cause Investigation ✅

### 1.1 Componentes Auditados

| Archivo | Líneas | Propósito | Riesgo |
|---------|--------|-----------|--------|
| `paths.py` | 132 | Normalización y validación de rutas | 🔴 Alto |
| `cm_track_operation.py` | 133 | Hook entry point | 🔴 Alto |
| `storage_jsonl.py` | 148 | Persistencia JSONL | 🟡 Medio |

### 1.2 Superficies de Ataque Identificadas

#### 1.2.1 Input: Hook JSON desde Claude Code

```python
# cm_track_operation.py:40-45
hook_input = json.load(sys.stdin)  # ⚠️ Input no confiable
tool_input = hook_input.get("tool_input", {})
file_path = tool_input.get("file_path")  # ⚠️ Puede ser malicioso
```

**Riesgo**: Un usuario podría pasar paths como:
- `../../../etc/passwd` (path traversal)
- `/etc/passwd` (lectura de sistema)
- `C:\Windows\System32\config\SAM` (Windows)

#### 1.2.2 Input: Paths desde `detect_repo()`

```python
# cm_track_operation.py:84-86
repo_info = detect_repo()
if not repo_info:
    return  # ⚠️ Fallback silencioso
```

**Riesgo**: Si `repo_info` es manipulado, paths válidos podrían ser rechazados.

---

## Phase 2: Análisis de Implementación ✅

### 2.1 Capas de Protección

#### Capa 1: `normalize_path()` (paths.py:14-59)

```python
def normalize_path(path: str, repo_root: Path) -> str:
    p = Path(path)

    # 1. Resolver a absoluto
    if p.is_absolute():
        abs_path = p.resolve()  # ✅ Elimina symlinks
    else:
        abs_path = (Path.cwd() / p).resolve()

    # 2. Verificar que está dentro del repo
    try:
        rel_path = abs_path.relative_to(repo_root.resolve())
    except ValueError:
        raise ValueError(f"Path '{path}' is outside repository root")

    # 3. Verificar que no hay .. components
    if ".." in normalized:
        raise ValueError(f"Path traversal not allowed: '{path}'")

    return normalized
```

**Análisis de Seguridad**:

| Check | Implementación | Efectividad |
|-------|----------------|-------------|
| **Path.resolve()** | ✅ Sí | Elimina symlinks y normaliza |
| **relative_to()** | ✅ Sí | Confina a repo root |
| **".." check** | ✅ Sí | Doble protección |
| **Null bytes** | ✅ Sí | Validación separada |

**⚠️ LIMITACIÓN ENCONTRADA**:

```python
# paths.py:54-57
if ".." in normalized:
    raise ValueError(f"Path traversal not allowed: '{path}'")
```

**Problema**: Este check es **post-resolución**, no pre-resolución.

**Escenario de ataque**:
```python
# Input malicioso
path = "src/../../../etc/passwd"

# Después de Path.resolve()
abs_path = Path("/etc/passwd")

# relative_to() falla → ValueError ✅ PROTEGIDO
```

**Conclusión**: El check de `".."` es redundante pero harmless. La verdadera protección viene de `relative_to()`.

#### Capa 2: `validate_path()` (paths.py:62-84)

```python
def validate_path(path: str) -> bool:
    if ".." in path:          # ❌ Insuficiente solo
        return False
    if path.startswith("/"):  # ✅ Bueno
        return False
    if "\0" in path:          # ✅ Excelente
        return False
    return True
```

**Análisis**:

| Check | Implementación | Efectividad |
|-------|----------------|-------------|
| **Traversal** | ⚠️ Débil | String match, puede ser evadido |
| **Absoluto** | ✅ Bueno | Previene rutas absolutas |
| **Null bytes** | ✅ Excelente | Previene inyección |

**⚠️ VULNERABILIDAD TEÓRICA**:

```python
# String match puede ser evadido con codificación
path = "src/..\x00./etc/passwd"  # \0 es detectado ✅
path = "src%2e%2e/etc/passwd"    # URL encoding - NO detectado ❌
```

**Nota**: En la práctica esto no es explotable porque Claude Code no decodifica URLs.

#### Capa 3: `get_relative_path()` (paths.py:87-106)

```python
def get_relative_path(file_path: str, repo_root: Path) -> Optional[str]:
    try:
        return normalize_path(file_path, repo_root)  # ✅ Reusa Capa 1
    except ValueError:
        return None  # ✅ Fail-safe
```

**Análisis**: ✅ **Excelente diseño** - reutiliza validación robusta y retorna `None` ante errores.

---

## Phase 3: Análisis de Casos de Ataque ✅

### 3.1 Matriz de Ataques Probados

| # | Ataque | Input | Resultado Esperado | Implementación | Status |
|---|--------|-------|-------------------|----------------|--------|
| 1 | **Path Traversal Básico** | `../../../etc/passwd` | Rechazar | ✅ `normalize_path()` lanza ValueError | ✅ PASS |
| 2 | **Traversal Mezclado** | `src/../../secret` | Rechazar | ✅ `validate_path()` retorna False | ✅ PASS |
| 3 | **Absoluto** | `/etc/passwd` | Rechazar | ✅ `validate_path()` retorna False | ✅ PASS |
| 4 | **Fuera del repo** | `/tmp/other/file.txt` | Rechazar | ✅ `normalize_path()` lanza ValueError | ✅ PASS |
| 5 | **Null Byte** | `src/app.py\x00.exe` | Rechazar | ✅ `validate_path()` retorna False | ✅ PASS |
| 6 | **Symlink Attack** | `symlink → /etc/passwd` | Resolver | ✅ `Path.resolve()` sigue symlink | ⚠️ DISCUSIÓN |
| 7 | **Windows UNC Path** | `\\server\share\file.txt` | Rechazar | ⚠️ NO implementado específicamente | ⚠️ PARTIAL |

### 3.2 Ataque #6: Symlink (DISCUSIÓN)

**Escenario**:
```bash
# Dentro del repo
ln -s /etc/passwd sensitive_file.txt

# Claude Code lee
Read tool: "sensitive_file.txt"

# ¿Qué pasa?
```

**Flujo de ejecución**:
```python
file_path = "/repo/sensitive_file.txt"
abs_path = Path(file_path).resolve()
# abs_path = Path("/etc/passwd")  ← Symlink resuelto

rel_path = abs_path.relative_to(repo_root)
# ValueError: '/etc/passwd' is not relative to '/repo'  ✅ RECHAZADO
```

**Conclusión**: ✅ **PROTEGIDO** - symlinks fuera del repo son rechazados correctamente.

**BUT**: Si el symlink apunta DENTRO del repo, es seguido intencionalmente (comportamiento correcto).

### 3.3 Ataque #7: Windows UNC Paths (PARTIAL)

**Input**:
```python
file_path = "\\\\server\\share\\file.txt"  # UNC path
```

**Comportamiento actual**:
```python
p = Path(path)  # Path("\\server\share\file.txt")
abs_path = p.resolve()  # Depende de OS

# En Windows: Could resolve to network share
# En Unix: Treats as relative path
```

**Problema**: No hay validación específica para UNC paths.

**Recomendación**: Agregar check explícito:
```python
if os.name == 'nt' and path.startswith("\\\\"):
    raise ValueError("UNC paths not allowed")
```

---

## Phase 4: Testing ✅

### 4.1 Cobertura de Tests de Seguridad

```bash
$ pytest tests/test_paths_security.py -v

tests/test_paths_security.py::test_normalize_rejects_traversal PASSED
tests/test_paths_security.py::test_normalize_rejects_outside_repo PASSED
tests/test_paths_security.py::test_validate_path_rejects_absolute PASSED
tests/test_paths_security.py::test_validate_path_rejects_traversal PASSED
tests/test_paths_security.py::test_validate_path_rejects_null_bytes PASSED
tests/test_paths_security.py::test_get_relative_path_invalid_returns_none PASSED
```

**Cobertura**: ✅ **Excelente** - 6 tests específicos de seguridad.

### 4.2 Tests Faltantes

| Caso | Prioridad | Razón |
|------|-----------|-------|
| UNC paths | Media | Solo Windows |
| URLs encoding | Baja | Claude Code no decodifica |
| Unicode normalization | Media | `℘` vs `P` puede evadir validación |

---

## 📊 Hallazgos de Seguridad

### 🔴 CRÍTICO

Ninguno encontrado.

### 🟡 MEDIO

| # | Issue | Impacto | Mitigación |
|---|-------|---------|------------|
| 1 | UNC paths no validados explícitamente | Windows-only | Agregar check para `\\\\` |

### 🟢 BAJO

| # | Issue | Impacto | Mitigación |
|---|-------|---------|------------|
| 1 | Check `".."` es post-resolución | Redundante | Documentar que es defense-in-depth |
| 2 | No hay límite de longitud de path | DoS teórico | Considerar MAX_PATH (4096) |

---

## ✅ Conclusiones

### Fortalezas

1. **Defense in Depth**: 3 capas independientes de validación
2. **Fail-Safe**: Retorna `None` o silencio ante errores (no crash)
3. **Test Coverage**: Tests específicos de seguridad
4. **Symlinks**: Correctamente manejados (resueltos y confinados)

### Debilidades

1. **UNC Paths**: No hay validación explícita para Windows
2. **Length Limits**: No hay límite en longitud de path (DoS vector)
3. **Unicode**: No hay normalización Unicode

### Recomendaciones

#### Inmediato

Ninguna - la implementación es segura para el caso de uso.

#### Corto Plazo

1. **Agregar check de UNC paths** (si Windows es soportado)
2. **Documentar el comportamiento con symlinks**
3. **Agregar test para paths muy largos**

#### Largo Plazo

1. **Considerar usar `pathlib.PurePath`** para validación sin acceso a filesystem
2. **Implementar longitud máxima** para prevenir DoS
3. **Unicode normalization** con `unicodedata.normalize()`

---

## Sources

- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [CWE-22: Improper Limitation of a Pathname](https://cwe.mitre.org/data/definitions/22.html)
- [Python Path Security Best Practices](https://docs.python.org/3/library/pathlib.html#security-considerations)

---

**Fin de Auditoría 1** 📌
