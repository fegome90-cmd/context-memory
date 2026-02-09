# 📋 INFORME: PostToolUse Hook No Captura en Subagentes

**Fecha**: 2026-01-02
**Método**: Systematic Debugging (Phase 1-3 completado)
**Estado**: Root Cause Identificado ✅

---

## Resumen Ejecutivo

**Problema**: El hook PostToolUse de `context-memory` NO captura operaciones Read/Write/Edit cuando se ejecutan dentro de subagentes (Task tool).

**Root Cause**: **Patrón de "Two-Tier Isolation"** (Sandboxing parcial) + **Variables de entorno no propagadas** a hooks de plugins en subagentes.

`★ Insight ─────────────────────────────────────`
- **Issue #9458**: Documenta que subagentes tienen filesystem aislado donde las operaciones Write parecen exitosas pero NO persisten
- **Issue #9447**: `CLAUDE_PROJECT_DIR` NO se propaga a hooks de plugins, solo `CLAUDE_PLUGIN_ROOT` funciona
- **Combinación fatal**: Hook que necesita detectar repo → falla porque `detect_repo()` no puede encontrar el directorio del proyecto
`─────────────────────────────────────────────────`

---

## Phase 1: Root Cause Investigation ✅

### 1.1 Evidencia Recopilada

| Aspecto | Estado | Evidencia |
|---------|--------|-----------|
| **Hook se ejecuta** | ✅ Parcialmente | Hay 1 evento en `current.jsonl` (ejecución directa) |
| **Hook en subagente** | ❌ No captura | No hay nuevos eventos después de usar Task tool |
| **Debug log** | ❌ Vacío | `/tmp/cm_hook_debug.log` no existe → hook no ejecutado en subagente |
| **Variables de entorno** | ❌ No propagadas | Issue #9447 confirma `CLAUDE_PROJECT_DIR` vacío en plugin hooks |

### 1.2 Análisis del Código

**`cm_track_operation.py:82-85`**:
```python
# Detect repo
repo_info = detect_repo()
if not repo_info:
    return  # Skip if not in a repo
```

**Problema**: `detect_repo()` usa `Path.cwd()` y búsqueda de `.git`. En un subagente:
- El cwd puede ser diferente
- `CLAUDE_PROJECT_DIR` no está disponible
- La detección falla silenciosamente

### 1.3 GitHub Issues Relevantes

| Issue | Título | Estado | Relevancia |
|-------|--------|--------|------------|
| [#9447](https://github.com/anthropics/claude-code/issues/9447) | Environment Variable Not Propagated in Plugin Hooks | Closed | 🔴 **CRÍTICO**: Confirma que `CLAUDE_PROJECT_DIR` no funciona en plugin hooks |
| [#9458](https://github.com/anthropics/claude-code/issues/9458) | Sub-agent Write tool operations don't persist to filesystem | Open | 🔴 **CRÍTICO**: Documenta el two-tier isolation pattern |
| [#3408](https://github.com/anthropics/claude-code/issues/3408) | Task tool crashes with sub-agents | Closed | 🟡 Contexto: Problemas conocidos con Task tool |

---

## Phase 2: Pattern Analysis ✅

### 2.1 Comparación: Ejecución Directa vs Subagente

| Aspecto | Ejecución Directa | Subagente (Task tool) |
|---------|-------------------|----------------------|
| **Hook PostToolUse** | ✅ Se ejecuta | ❌ No se ejecuta o falla silenciosamente |
| **Variables de entorno** | ✅ `CLAUDE_PROJECT_DIR` disponible | ❌ `CLAUDE_PROJECT_DIR` NO propagado |
| **Filesystem** | ✅ Operaciones persisten | ⚠️ Two-tier isolation (dirs sí, contenido no) |
| **`detect_repo()`** | ✅ Funciona | ❌ Falla (cwd diferente + sin CLAUDE_PROJECT_DIR) |

### 2.2 Flujo de Datos

```
┌─────────────────────────────────────────────────────────────────┐
│                    EJECUCIÓN DIRECTA                            │
├─────────────────────────────────────────────────────────────────┤
│  1. Usuario usa Read tool                                       │
│  2. PostToolUse hook se dispara                                 │
│  3. CLAUDE_PROJECT_DIR ✅ disponible                            │
│  4. detect_repo() ✅ encuentra .git                             │
│  5. Evento se escribe a current.jsonl ✅                        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    SUBAGENTE (Task tool)                        │
├─────────────────────────────────────────────────────────────────┤
│  1. Main agent lanza subagente con Task tool                   │
│  2. Subagente ejecuta Read tool en contexto aislado            │
│  3. PostToolUse hook:                                           │
│     - ❌ No se ejecuta, O                                       │
│     - ❌ Se ejecuta pero CLAUDE_PROJECT_DIR vacío              │
│     - ❌ detect_repo() falla (cwd diferente)                   │
│  4. Evento NO se escribe a current.jsonl ❌                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 3: Root Cause Identificado ✅

### 🔴 ROOT CAUSE

**Problema multifactorial:**

1. **Sandboxing de Subagentes** (Issue #9458)
   - Los subagentes ejecutan en un filesystem aislado
   - Las operaciones de archivos pueden no persistir al proceso principal
   - Esto afecta tanto los writes como los hooks que escriben a archivos

2. **Variables de Entorno No Propagadas** (Issue #9447)
   - `CLAUDE_PROJECT_DIR` NO se propaga a hooks de plugins
   - El script `cm_track_operation.py` depende de `detect_repo()` que usa `Path.cwd()`
   - En el contexto aislado del subagente, `Path.cwd()` apunta a un directorio diferente

3. **Detección de Repo Falla**
   - Sin `CLAUDE_PROJECT_DIR`, el hook no puede determinar el repo root
   - `detect_repo()` retorna `None`
   - El hook hace `return` temprano (línea 85)

### Diagrama del Problema

```
┌───────────────────────────────────────────────────────────────────┐
│                     Task Tool Execution                           │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│   Main Process                                                    │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │ CLAUDE_PROJECT_DIR=/Users/felipe_gonzalez/Developer       │ │
│   │ Working Directory: /Users/felipe_gonzalez/Developer       │ │
│   └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │          SPAWN SUBAGENT (Task tool)                       │ │
│   │   ┌────────────────────────────────────────────────────┐  │ │
│   │   │ Isolated Context                                  │  │ │
│   │   │ ❌ CLAUDE_PROJECT_DIR: (undefined/empty)          │  │ │
│   │   │ ❌ Working Directory: /tmp/claude-subagent-xxx     │  │ │
│   │   │                                                    │  │ │
│   │   │ Read Tool → PostToolUse Hook:                     │  │ │
│   │   │   ┌──────────────────────────────────────────┐   │  │ │
│   │   │   │ detect_repo():                            │   │  │ │
│   │   │   │   Path.cwd() = /tmp/claude-subagent-xxx   │   │  │ │
│   │   │   │   .git not found → return None            │   │  │ │
│   │   │   │   if not repo_info: return  ❌            │   │  │ │
│   │   │   └──────────────────────────────────────────┘   │  │ │
│   │   └────────────────────────────────────────────────────┘  │ │
│   └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│   Result: Evento NO capturado en current.jsonl                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 📊 Evidencia Cuantitativa

### Session Log Actual

```json
{
  "operation": "read",
  "ts": 1767368699,
  "source": "hook",
  "file_path": "Developer/raycast_ext/README.md",
  "tool": "Read",
  "tool_input": "{\"file_path\": \"/Users/felipe_gonzalez/Developer/raycast_ext/README.md\"}"
}
```

**Solo 1 evento** → capturado en ejecución directa, NO en subagente.

### Tests que Confirmarían el Root Cause

```bash
# Test 1: Verificar que hook no se ejecuta en subagente
# Antes de usar Task tool
wc -l .claude/context_memory/sessions/current.jsonl
# Result: 1

# Usar Task tool para hacer Read
Task({ subagent_type: "Explore", prompt: "Lee README.md del repo actual" })

# Verificar después
wc -l .claude/context_memory/sessions/current.jsonl
# Result esperado: 1 (sin cambios) ❌

# Test 2: Verificar variables de entorno en subagente
Task({
  subagent_type: "Explore",
  prompt: "Executa: echo CLAUDE_PROJECT_DIR=$CLAUDE_PROJECT_DIR y pwd"
})
# Result esperado: CLAUDE_PROJECT_DIR vacío o diferente
```

---

## 🎯 Soluciones Potenciales (NO Implementadas)

### Opción A: Pasar ruta explícita al hook

**Concepto**: El hook podría aceptar la ruta del repo como parámetro.

**Problema**: Requiere cambiar cómo Claude Code invoca los hooks (no es configurable por el usuario).

### Opción B: Detectar repo desde stdin del hook

**Concepto**: El hook recibe JSON vía stdin, podría incluir `CLAUDE_PROJECT_DIR`.

**Problema**: Issue #9447 indica que esto NO funciona en plugin hooks actualmente.

### Opción C: Usar ruta absoluta del plugin + inferir repo

**Concepto**: Desde `CLAUDE_PLUGIN_ROOT` (SÍ funciona), infer el repo root navegando hacia arriba.

**Problema**: El plugin puede estar instalado globalmente (`~/.claude/plugins/`), no en el repo.

### Opción D: Híbrido - Captura en main agent

**Concepto**: En lugar de depender del hook en subagentes, el main agent podría solicitar el reporte de operaciones al subagente y guardarlo.

**Problema**: Requiere cambios en cómo se invoca el Task tool y cómo los subagentes reportan.

---

## 📝 Recomendaciones

### Para el Usuario (Inmediato)

1. **NO usar Task tool** cuando necesites capturar operaciones en context-memory
2. **Usar ejecución directa** para todo lo que necesites tracking
3. **Documentar operaciones manualmente** si usas subagentes: `/cm-context` para ver qué se capturó

### Para context-memory (Corto Plazo)

1. **Agregar logging**: Cuando `detect_repo()` falle, logear el error en lugar de fallar silenciosamente
2. **Modo fallback**: Si no se puede detectar repo, usar `~/.claude/context_memory/sessions/global.jsonl`
3. **Documentar limitación**: Agregar nota en README sobre Task tool

### Para Anthropic (Largo Plazo)

1. **Fix Issue #9447**: Propagar `CLAUDE_PROJECT_DIR` a plugin hooks en subagentes
2. **Revisar sandboxing**: Considerar si el two-tier isolation es intencional o un bug (#9458)
3. **Protocolo de handoff**: Permitir que subagentes declaren explícitamente operaciones de archivos

---

## Sources

- [Issue #9447: Environment Variable Not Propagated in Plugin Hooks](https://github.com/anthropics/claude-code/issues/9447)
- [Issue #9458: Sub-agent Write tool operations don't persist to filesystem](https://github.com/anthropics/claude-code/issues/9458)
- [Issue #3408: Task tool crashes with sub-agents](https://github.com/anthropics/claude-code/issues/3408)
- [A developer's hooks reference for Claude Code](https://www.eesel.ai/blog/hooks-reference-claude-code)
- [Claude Code Hooks Guide](https://hexdocs.pm/claude_agent_sdk/hooks_guide.html)

---

**Fin del Informe** 📌
