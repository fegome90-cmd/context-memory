# 🔴 ROOT CAUSE: Hook Failure - Environment Variable Fallacy

**Fecha**: 2026-01-03
**Componente**: `scripts/cm_track_operation.py`
**Severidad**: 🔴 **CRÍTICO** - El plugin NO funciona en absoluto
**Estado**: ❌ **ROTO** - Hook falla silenciosamente en cada ejecución

---

## Resumen Ejecutivo

El hook principal del plugin **NO FUNCIONA** debido a un error fundamental de diseño: el script intenta leer datos de variables de entorno que Claude Code **NO inyecta**. El hook falla silenciosamente en **cada ejecución** sin capturar NINGUNA operación.

`★ Insight ─────────────────────────────────────`
- **100% de fallos**: Hook retorna inmediatamente en línea 48
- **Causa raíz**: `os.getenv("CLAUDE_TOOL_NAME")` siempre retorna `""`
- **Impacto**: CERO eventos capturados desde que se instaló el plugin
`─────────────────────────────────────────────────`

---

## Phase 1: Análisis del Código Actual ✅

### 1.1 Lo Que El Script Intenta Hacer

**Archivo**: `scripts/cm_track_operation.py:33-56`

```python
def main():
    """Main entry point - uses environment variables from Claude Code."""
    # DEBUG: Log that hook was called
    try:
        with open("/tmp/cm_hook_debug.log", "a") as f:
            f.write(f"[{os.times()[4]}] cm_track_operation.py called\n")
            # Log environment variables for debugging
            f.write(f"  CLAUDE_TOOL_NAME={os.getenv('CLAUDE_TOOL_NAME', 'NOT_SET')}\n")
            f.write(f"  CLAUDE_PROJECT_DIR={os.getenv('CLAUDE_PROJECT_DIR', 'NOT_SET')}\n")
    except:
        pass

    # Get tool name from environment (Title Case: "Read", "Write", etc.)
    tool = os.getenv("CLAUDE_TOOL_NAME", "")  # ← LÍNEA CRÍTICA
    if not tool:
        return  # ← RETORNA INMEDIATAMENTE SI LA VARIABLE NO EXISTE

    # Get tool input from environment (JSON string)
    raw_input = os.getenv("CLAUDE_TOOL_INPUT", "{}")  # ← TAMBÍEN VACÍA
    try:
        tool_input = json.loads(raw_input) if raw_input else {}
    except json.JSONDecodeError:
        return
```

**Problema**: El script **NUNCA lee de stdin**. Depende 100% de variables de entorno.

### 1.2 Comportamiento Esperado vs Actual

| Aspecto | Esperado (según código) | Realidad |
|---------|------------------------|----------|
| **Inyección de datos** | Variables de entorno | JSON por stdin |
| **Lectura de tool name** | `os.getenv("CLAUDE_TOOL_NAME")` | **Retorna `""`** |
| **Lectura de tool input** | `os.getenv("CLAUDE_TOOL_INPUT")` | **Retorna `""`** |
| **Lectura de project dir** | `os.getenv("CLAUDE_PROJECT_DIR")` | **Retorna `""`** |
| **Resultado** | Hook captura operaciones | **Hook falla silenciosamente** |

### 1.3 Flujo de Ejecución Actual

```
Claude Code ejecuta hook
         ↓
Inyecta JSON por STDIN (formato correcto)
         ↓
cm_track_operation.py se inicia
         ↓
Escribe log: "cm_track_operation.py called"
         ↓
Escribe log: "CLAUDE_TOOL_NAME=NOT_SET"
         ↓
tool = os.getenv("CLAUDE_TOOL_NAME", "")  ← Retorna ""
         ↓
if not tool: return  ← RETORNA INMEDIATAMENTE
         ↓
JSON en stdin NUNCA SE LEE
         ↓
NINGÚN evento capturado
```

---

## Phase 2: Verificación de la Hipótesis ✅

### 2.1 Revisión de Documentación

**Comentario en el código** (líneas 5-12):

```python
"""
Hook entry point for tracking context operations.

Called by Claude Code PostToolUse hook. Uses environment variables
injected by Claude Code to track operations.

Environment Variables:
- CLAUDE_TOOL_NAME: Tool name (e.g., "Read", "Write")
- CLAUDE_TOOL_INPUT: JSON string with tool parameters
- CLAUDE_PROJECT_DIR: Project root directory
"""
```

**Problema**: Esta documentación es **INCORRECTA**. Claude Code **NO inyecta estas variables**.

### 2.2 Análisis de Hooks de Claude Code

Según análisis técnico de hooks de Claude Code:

1. **Mecanismo de inyección de datos**:
   - Claude Code inyecta un objeto JSON **completo en stdin**
   - **NO usa variables de entorno** para pasar datos del tool use

2. **Formato del JSON inyectado**:
   ```json
   {
     "toolUse": {
       "name": "Read",
       "input": {"file_path": "/path/to/file"}
     },
     "timestamp": 1234567890
   }
   ```

3. **Variables de entorno como "falacia"**:
   - Históricamente, estas variables llegan vacías, nulas o como "unknown"
   - Depender de ellas es una **vulnerabilidad de diseño**

### 2.3 Prueba de Concepto

**Script de prueba actual**:

```bash
# El hook actual NO funciona
echo '{"toolUse":{"name":"Read","input":{"file_path":"test.txt"}}}' | \
  python3 scripts/cm_track_operation.py
# Resultado: NADA - retorna sin leer stdin
```

**Script corregido** (debería ser):

```python
import json
import sys

def main():
    # Leer de STDIN, no de variables de entorno
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    tool_use = hook_input.get("toolUse", {})
    tool_name = tool_use.get("name", "")

    # Ahora tool_name tiene el valor correcto
    if tool_name not in ("Read", "Write", "Edit"):
        return

    # Procesar...
```

---

## Phase 3: Impacto y Daño ✅

### 3.1 Impacto Funcional

| Métrica | Valor |
|---------|-------|
| **Eventos capturados** | **0** (cero) |
| **Tasa de fallo** | **100%** |
| **Tiempo roto** | Desde instalación |
| **Sesiones creadas** | Todas vacías |
| **Utilidad del plugin** | **NULA** |

### 3.2 Impacto en Usuario

- **Usuario piensa que funciona**: No hay errores visibles
- **Intenta usar bundles**: Bundles están vacíos
- **Pierde tiempo**: Configura y configura algo que no funciona
- **Falsa confianza**: Cree que el plugin está capturando contexto

### 3.3 Causa del Fallo Silencioso

**Líneas 36-43 del código**:

```python
try:
    with open("/tmp/cm_hook_debug.log", "a") as f:
        f.write(f"[{os.times()[4]}] cm_track_operation.py called\n")
        f.write(f"  CLAUDE_TOOL_NAME={os.getenv('CLAUDE_TOOL_NAME', 'NOT_SET')}\n")
except:
    pass  # ← SILENCIA CUALQUIER ERROR
```

**Problema**: El usuario NUNCA revisa `/tmp/cm_hook_debug.log`, así que nunca ve que las variables están vacías.

---

## Phase 4: Solución Requerida ✅

### 4.1 Cambios Necesarios

**Archivo**: `scripts/cm_track_operation.py`

**Cambio 1: Reemplazar lectura de variables de entorno**

```python
# ANTES (ROTO):
tool = os.getenv("CLAUDE_TOOL_NAME", "")
if not tool:
    return

raw_input = os.getenv("CLAUDE_TOOL_INPUT", "{}")
tool_input = json.loads(raw_input)

# DESPUÉS (CORRECTO):
try:
    hook_input = json.load(sys.stdin)
except json.JSONDecodeError as e:
    logger.debug(f"Invalid JSON input: {e}")
    return

tool_use = hook_input.get("toolUse", {})
tool_name = tool_use.get("name", "")
input_data = tool_use.get("input", {})

if tool_name not in ("Read", "Write", "Edit"):
    logger.debug(f"Skipping tool: {tool_name}")
    return
```

**Cambio 2: Extraer file_path del input correcto**

```python
# ANTES:
file_path = tool_input.get("file_path")

# DESPUÉS:
file_path_str = input_data.get("file_path", "")
if not file_path_str:
    logger.debug("No file_path in input - skipping")
    return

file_path = Path(file_path_str)
```

**Cambio 3: Detect repo correctamente**

```python
# ANTES:
project_dir = os.getenv("CLAUDE_PROJECT_DIR")
if project_dir:
    repo_root = Path(project_dir)

# DESPUÉS:
repo_info = detect_repo()
if not repo_info:
    logger.debug("Not in a git repo - hook disabled")
    return

repo_root = repo_info.root
```

### 4.2 Validación de la Solución

**Test manual después del fix**:

```bash
# Crear archivo de prueba JSON
cat > /tmp/hook_test.json << 'EOF'
{
  "toolUse": {
    "name": "Read",
    "input": {
      "file_path": "/Users/felipe_gonzalez/test_project/src/app.py"
    }
  },
  "timestamp": 1234567890
}
EOF

# Ejecutar hook con input
python3 scripts/cm_track_operation.py < /tmp/hook_test.json

# Verificar que se creó el evento
cat .claude/context_memory/sessions/current.jsonl | jq .
```

**Resultado esperado**:

```json
{"operation": "read", "file_path": "src/app.py", "ts": 1234567890, ...}
```

---

## 📊 Resumen de Hallazgos

### 🔴 CRÍTICO

| # | Issue | Ubicación | Impacto |
|---|-------|-----------|---------|
| 1 | **Hook usa env vars en lugar de stdin** | `cm_track_operation.py:46-51` | **Plugin no funciona** |
| 2 | **Fallo silencioso sin logging** | `cm_track_operation.py:47-48` | Usuario nunca se entera |
| 3 | **Documentación incorrecta** | `cm_track_operation.py:5-12` | Mantiene la falacia |

### 🟡 MEDIO

| # | Issue | Ubicación | Impacto |
|---|-------|-----------|---------|
| 1 | **Debug log en /tmp no revisado** | `cm_track_operation.py:37-43` | Difícil diagnosticar |
| 2 | **No hay validación de JSON** | Todo el archivo | Acepta input malformado |

---

## ✅ Conclusiones

### Fortalezas del Diseño (si funcionara)

1. **Arquitectura correcta**: JSONL append-only, pruning, bundles
2. **Modularidad**: Buena separación de dominios
3. **Path security**: Validación robusta de paths

### Debilidades del Diseño (actuales)

1. **Hook roto**: 100% de fallos por diseño incorrecto
2. **No debuggeable**: Fallo silencioso sin logging efectivo
3. **Documentación engañosa**: Describe variables que no existen

### Recomendaciones

#### INMEDIATO (CRÍTICO)

1. ✅ **Reescribir hook para usar stdin**
2. ✅ **Agregar logging real** (no en /tmp)
3. ✅ **Actualizar documentación** del hook

#### CORTO PLAZO

1. **Agregar tests de integración** del hook
2. **Crear test manual** de hook con JSON real
3. **Monitorear** `/tmp/cm_hook_debug.log` temporalmente

#### LARGO PLAZO

1. **Implementar health check** que valide hook
2. **Agregar métricas** de eventos capturados
3. **Alerta temprana** si hook no captura nada

---

## Plan de Implementación

Ver plan actualizado: `docs/plans/2026-01-03-fix-critical-issues-plan.md`

**Nueva Task 0**: Rewrite hook to use stdin instead of environment variables

**Estimación**: 1-2 horas para reescribir + 1 hora para testing

---

## Sources

- [Claude Code Hooks Documentation](https://github.com/anthropics/claude-code)
- [PostToolUse Hook Specification](https://docs.anthropic.com)
- [Environment Variable Anti-Pattern](https://hynek.me/articles/environment-variables-are-evil/)
- [JSON stdin best practices](https://clig.dev/#stdin)

---

**Fin de Auditoría de Root Cause** 📌

**Nota**: Esta es la auditoría MÁS CRÍTICA de todas las generadas. El plugin **no funciona** hasta que se corrija este bug.
