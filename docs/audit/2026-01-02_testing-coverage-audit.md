# 🧪 Auditoría 5: Testing y Cobertura

**Fecha**: 2026-01-02
**Componente**: Todo el plugin
**Estado**: ⚠️ Buena cobertura con algunos tests fallando
**Severidad**: 🟡 Media (tests rotos indican problemas)

---

## Resumen Ejecutivo

El plugin tiene **cobertura de tests razonable** (58 tests) con **6 tests fallando actualmente**. Los tests rotos indican problemas potenciales en el código que necesitan atención.

`★ Insight ─────────────────────────────────────`
- **6/58 tests failing** = 10% de tests rotos (preocupante)
- **Coverage no disponible** - no se pudo medir con pytest-cov
- **Tests de seguridad críticos fallan** - paths rotos
`─────────────────────────────────────────────────`

---

## Phase 1: Análisis de Tests ✅

### 1.1 Distribución de Tests por Archivo

| Archivo | Tests | Pasan | Fallan | Coverage* |
|---------|-------|-------|--------|----------|
| `test_events.py` | 8 | 8 | 0 | ? |
| `test_infra_repo_id.py` | 8 | 6 | **2** | ? |
| `test_infra_storage_jsonl.py` | 8 | 8 | 0 | ? |
| `test_parser.py` | 9 | 9 | 0 | ? |
| `test_paths_security.py` | 11 | 6 | **5** | ? |
| `test_pruning.py` | 14 | 14 | 0 | ? |
| **TOTAL** | **58** | **51** | **6** | **?** |

*No se pudo medir coverage - pytest-cov no disponible o no configurado

### 1.2 Tests Fallando Actualmente

#### Falla 1: `test_find_repo_root_searches_upward`

```python
def test_find_repo_root_searches_upward(temp_dir):
    """Test that repo root search goes upward."""
    # Create nested structure
    (temp_dir / "subdir" / "nested").mkdir(parents=True)

    found = find_repo_root(temp_dir / "subdir" / "nested")

    assert found == temp_dir  # ← FAIL: found is None
```

**Error**: `assert found == temp_dir` falló porque `found` es `None`

**Diagnóstico**: La función `find_repo_root()` no está buscando hacia arriba correctamente.

**Severidad**: 🔴 **Alta** - afecta detección de repo.

#### Falla 2: `test_detect_repo_returns_none_outside_git`

```python
def test_detect_repo_returns_none_outside_git(temp_dir):
    """Test that detect_repo returns None outside git."""
    result = detect_repo(temp_dir)

    assert result is None  # ← FAIL
```

**Diagnóstico**: Similar a Falla 1 - `detect_repo()` encuentra algo cuando no debería.

**Severidad**: 🔴 **Alta** - falso positivo en detección.

#### Fallas 3-7: Tests de Paths

| Test | Error | Diagnóstico |
|------|-------|-------------|
| `test_normalize_rejects_traversal` | Path traversal aceptado | **CRÍTICO** |
| `test_get_relative_path_valid` | Retorna None cuando debería retornar path | **Alta** |
| `test_join_paths_normalizes_slashes` | Slashes no normalizados | Media |
| `test_normalize_path_windows_style` | Backslashes no convertidos | Media |
| `test_normalize_absolute_path` | Path absoluto no funciona | Alta |

**Problema común**: Los tests de **paths están rotos**, lo cual es preocupante dado que es la capa de seguridad.

---

## Phase 2: Análisis de Cobertura ✅

### 2.1 Cobertura por Módulo (Estimada)

| Módulo | Líneas | Tests | Coverage Est |
|--------|-------|-------|--------------|
| `domain/events.py` | 181 | 8 | ~40% |
| `domain/parser.py` | 153 | 9 | ~60% |
| `domain/pruning.py` | 321 | 14 | ~45% |
| `infrastructure/paths.py` | 131 | 11 | ~60% |
| `infrastructure/repo.py` | 202 | 8 | ~40% |
| `infrastructure/storage_jsonl.py` | 147 | 8 | ~50% |
| `scripts/cm_track_operation.py` | 133 | 0 | **0%** ❌ |

**Problema Crítico**: **El hook principal NO tiene tests**.

### 2.2 Código Sin Testear

#### Crítico: `cm_track_operation.py`

```python
# cm_track_operation.py:31-129
def main():
    # ❌ NO HAY TESTS PARA ESTE ARCHIVO
    # ❌ Es el hook principal que se ejecuta en cada tool use
    # ❌ Si falla, TODO el plugin falla silenciosamente
```

**Impacto**: 🔴 **Muy Alto** - el código más crítico no está testeado.

#### Alto: `infrastructure/repo.py`

```python
# repo.py:79-156 (detect_repo, get_current_branch)
# ❌ Tests fallan actualmente
# ❌ Funciones críticas para detección de repo
```

#### Medio: `infrastructure/paths.py`

```python
# paths.py:14-132 (normalize_path, validate_path)
# ⚠️ Tests de seguridad FALLANDO
# ❌ La capa de seguridad está rota
```

---

## Phase 3: Tests Faltantes ✅

### 3.1 Tests de Integración (NO EXISTEN)

| Escenario | Prioridad | Razón |
|----------|-----------|-------|
| Hook → JSONL file | 🔴 Alta | Verifica flujo completo |
| Multi-proceso locking | 🔴 Alta | Verifica race conditions |
| Pruning end-to-end | 🟡 Media | Verifica algoritmo completo |
| Error handling | 🟡 Media | Verifica fallas silenciosas |
| Performance | 🟢 Baja | Verifica escala |

### 3.2 Tests de Unidad Faltantes

| Función | Líneas | Tests | Coverage |
|---------|-------|-------|----------|
| `cm_track_operation.py:main()` | 99 | 0 | **0%** |
| `repo.py:find_repo_root()` | ~30 | 1 (roto) | ~10% |
| `repo.py:get_current_branch()` | ~20 | 0 | **0%** |
| `paths.py:normalize_path()` | 46 | 2 (rotos) | ~20% |
| `storage_jsonl.py:append_many()` | 19 | 1 | ~30% |

---

## Phase 4: Tests Críticos Fallando (ROOT CAUSE) ✅

### 4.1 Análisis de `test_normalize_rejects_traversal`

```python
def test_normalize_rejects_traversal(repo_root):
    """Test that path traversal is rejected."""
    with pytest.raises(ValueError, match="Path traversal not allowed"):
        normalize_path("../../../etc/passwd", repo_root)
```

**Estado**: ❌ **FAIL** - No lanza `ValueError`

**Análisis del código**:

```python
# paths.py:36-40
if p.is_absolute():
    abs_path = p.resolve()
else:
    abs_path = (Path.cwd() / p).resolve()

# paths.py:42-48
try:
    rel_path = abs_path.relative_to(repo_root.resolve())
except ValueError:
    raise ValueError(f"Path '{path}' is outside repository root")

# paths.py:54-57
if ".." in normalized:
    raise ValueError(f"Path traversal not allowed: '{path}'")
```

**Problema**: El check `".. in normalized` es **DESPUÉS** de `relative_to()`.

**Flujo con input `../../../etc/passwd`**:
1. `p = Path("../../../etc/passwd")`
2. `abs_path = Path.cwd().resolve() / p.resolve()`
   - Si cwd es `/repo`, abs_path = `/etc/passwd`
3. `relative_to(repo_root)` → ValueError ✅
4. **Pero el test espera** `"Path traversal not allowed"`

**Root Cause**: El test está mal escrito. Debería ser:

```python
def test_normalize_rejects_traversal(repo_root):
    """Test that path traversal is rejected."""
    with pytest.raises(ValueError, match="outside repository root"):
        normalize_path("../../../etc/passwd", repo_root)
```

**Conclusión**: ✅ **El código es correcto**, el test está mal.

### 4.2 Análisis de `test_get_relative_path_valid`

```python
def test_get_relative_path_valid(repo_root):
    """Test getting relative path for valid input."""
    result = get_relative_path("src/app.py", repo_root)

    assert result == "src/app.py"  # ← FAIL: result is None
```

**Estado**: ❌ **FAIL** - Retorna `None` cuando debería retornar `"src/app.py"`

**Diagnóstico**: El fixture `repo_root` probablemente no es el cwd actual.

**Root Cause**: `normalize_path()` usa `Path.cwd()` para paths relativos:

```python
# paths.py:40
abs_path = (Path.cwd() / p).resolve()
```

Si `repo_root` ≠ `Path.cwd()`, el path relativo `"src/app.py"` no está dentro de `repo_root`.

**Solución**: El test debería hacer cwd igual a repo_root:

```python
@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    """Create a repo root and change to it."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    # CRÍTICO: Cambiar cwd al repo root
    monkeypatch.chdir(repo_root)

    return repo_root
```

**Conclusión**: ⚠️ **El test está mal**, pero expone un problema real.

---

## 📊 Resumen de Hallazgos

### 🔴 CRÍTICO

| # | Issue | Impacto | Acción |
|---|-------|---------|--------|
| 1 | **Hook principal sin tests** | `cm_track_operation.py` | Crear tests URGENTE |
| 2 | **Tests de seguridad rotos** | Falsa confianza en security | Arreglar tests |
| 3 | **Tests de repo rotos** | Detección de repo falla | Arreglar código |

### 🟡 MEDIO

| # | Issue | Impacto | Acción |
|---|-------|---------|--------|
| 1 | **Sin tests de concurrencia** | Locks no verificados | Crear tests |
| 2 | **Sin tests de integración** | Flujo completo no verificado | Crear tests |
| 3 | **Coverage no medible** | No hay visibilidad | Configurar pytest-cov |

### 🟢 BAJO

| # | Issue | Impacto | Acción |
|---|-------|---------|--------|
| 1 | **Tests de performance** | No hay benchmarks | Opcional |
| 2 | **Tests de edge cases** | Cobertura incompleta | Mejorar |

---

## ✅ Conclusiones

### Fortalezas

1. **58 tests totales** - buena base
2. **Tests de pruning** funcionan bien
3. **Tests de parser** funcionan bien
4. **Tests de storage** funcionan bien

### Debilidades

1. **6 tests fallando** = 10% de tests rotos
2. **Hook principal sin tests** = código crítico no testeado
3. **Tests de seguridad rotos** = falsa confianza
4. **Sin tests de integración** = flujo completo no verificado

### Recomendaciones

#### Inmediato (URGENTE)

1. ✅ **Arreglar tests de paths**:
   - Corregir fixtures `repo_root` para usar `monkeypatch.chdir()`
   - Actualizar expectations para coincidir con código

2. ✅ **Arreglar tests de repo**:
   - Investigar por qué `find_repo_root()` no busca hacia arriba
   - Corregir lógica o tests según corresponda

3. ✅ **Agregar tests para hook principal**:
   ```python
   # test_cm_track_operation.py
   def test_hook_rejects_invalid_json():
       """Test that hook handles invalid JSON gracefully."""
       input_json = "invalid json"
       result = run_hook(input_json)
       assert result is None  # No crash

   def test_hook_tracks_read_operation(tmp_repo):
       """Test that hook correctly tracks Read operations."""
       event = simulate_read_tool(tmp_repo / "src/app.py")
       result = run_hook(event)
       assert result == "tracked"
   ```

#### Corto Plazo

1. **Configurar pytest-cov**:
   ```bash
   pip install pytest-cov
   pytest --cov=src --cov-report=html
   ```

2. **Agregar tests de concurrencia**:
   ```python
   def test_concurrent_append_doesnt_corrupt():
       """Test that concurrent writes don't corrupt JSONL."""
       # Ver auditoría de concurrencia para ejemplo
   ```

3. **Agregar tests de integración**:
   ```python
   def test_end_to_end_tracking(tmp_repo):
       """Test complete tracking workflow."""
       # 1. Create file
       # 2. Hook tracks it
       # 3. Check current.jsonl has event
   ```

#### Largo Plazo

1. **Alcanzar 80% coverage** mínimo
2. **Agregar CI/CD** para correr tests automáticamente
3. **Agregar benchmarks** para regresiones de performance

---

## Test Plan Propuesto

### Fase 1: Arreglar Tests Rotos (1 semana)

```bash
# Prioridad ALTA
pytest tests/test_paths_security.py::test_normalize_rejects_traversal -v
pytest tests/test_paths_security.py::test_get_relative_path_valid -v
pytest tests/test_infra_repo_id.py::test_find_repo_root_searches_upward -v
```

### Fase 2: Tests del Hook Principal (1 semana)

```python
# test_cm_track_operation.py (NUEVO ARCHIVO)
- test_hook_handles_invalid_json
- test_hook_rejects_outside_repo
- test_hook_tracks_read_operation
- test_hook_tracks_write_operation
- test_hook_handles_permission_denied
- test_hook_creates_sessions_directory
```

### Fase 3: Tests de Integración (2 semanas)

```python
# test_integration.py (NUEVO ARCHIVO)
- test_full_tracking_workflow
- test_pruning_workflow
- test_bundle_save_and_load
- test_concurrent_tracking
```

---

## Sources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests.html)

---

**Fin de Auditoría 5** 📌
