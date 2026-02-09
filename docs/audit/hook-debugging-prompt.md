# Prompt para Debugging de Hooks - Context Memory Plugin

## Contexto del Problema

El plugin `context-memory` tiene hooks PostToolUse configurados pero **NO se están ejecutando**. Necesito que investigues por qué.

## Síntomas

1. **Debug log vacío**: `/tmp/cm_hook_debug.log` nunca se crea
2. **Sin eventos capturados**: `.claude/context_memory/sessions/current.jsonl` tiene 0 líneas
3. **Script funciona manualmente**: Probado con `echo '{"tool": "Read", ...}' | python3 script.py` ✅

## Configuración Actual

### Plugin Registration
**Archivo**: `~/.claude/plugins/installed_plugins.json`

```json
"context-memory@local": [{
  "scope": "user",
  "installPath": "/Users/felipe_gonzalez/.claude/plugins/context-memory",
  "version": "1.0.0",
  "isLocal": true
}]
```

### Plugin Structure
```
~/.claude/plugins/context-memory/
├── .claude-plugin/
│   └── plugin.json          # Manifest
├── hooks/
│   ├── __init__.py
│   └── hooks.json           # PostToolUse config
└── scripts/
    └── cm_track_operation.py
```

### hooks.json
```json
{
  "description": "Context Memory Plugin - Track Read/Write/Edit/MultiEdit operations",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /Users/felipe_gonzalez/.claude/plugins/context-memory/scripts/cm_track_operation.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### Script (cm_track_operation.py)
```python
import os
import json

def main():
    # DEBUG log
    with open("/tmp/cm_hook_debug.log", "a") as f:
        f.write(f"Hook called at {os.times()[4]}\n")
        f.write(f"CLAUDE_TOOL_NAME={os.getenv('CLAUDE_TOOL_NAME', 'NOT_SET')}\n")

    # Get tool from ENV (not stdin!)
    tool = os.getenv("CLAUDE_TOOL_NAME", "")
    if not tool:
        return

    # ... rest of logic
```

## Plugins que SÍ Funcionan (Referencia)

### hookify (oficial)
- Path: `~/.claude/plugins/cache/claude-plugins-official/hookify/6d3752c000e2/`
- Registration: `hookify@claude-plugins-official`
- Structure: Tiene `hooks/hooks.json` con `PostToolUse`
- **Sus hooks SÍ funcionan**

### test-hook (local)
- Path: `~/.claude/plugins/test-hook/`
- Registration: `test-hook@local`
- Structure: Similar a context-memory
- **¿Funcionan sus hooks? Desconocido**

## Información de Referencia

Según análisis previo de "Indy Dev Dan" sobre hooks en Claude Code:

1. **Claude Code usa variables de entorno** para injectar contexto al hook:
   - `CLAUDE_TOOL_NAME`: Nombre de herramienta ("Read", "Write", etc.)
   - `CLAUDE_TOOL_INPUT`: JSON string con parámetros
   - `CLAUDE_PROJECT_DIR`: Directorio del proyecto

2. **PostToolUse solo dispara para operaciones del usuario**, no de subagentes

3. **Plugins hacen snapshot al inicio** - cambios requieren reinicio

4. **El `matcher` debe usar Title Case**: `"Read|Write|Edit"` (no minúsculas)

## Tarea de Investigación

Por favor, analiza:

1. **¿Es correcto el formato de hooks.json para un plugin local?**
   - Compara con hookify y test-hook
   - Verifica si falta algún campo requerido

2. **¿Es correcto el registro en installed_plugins.json?**
   - Compara `context-memory@local` vs `test-hook@local` vs plugins oficiales
   - ¿Hay diferencia en cómo se registran plugins locales vs oficiales?

3. **¿El path del script es correcto?**
   - Ruta absoluta vs relativa vs `${CLAUDE_PLUGIN_ROOT}`

4. **¿Hay alguna otra configuración necesaria?**
   - ¿Falta algún campo en plugin.json?
   - ¿Se necesita activar el plugin de alguna forma?

5. **¿Cómo se cargan los plugins locales vs los del marketplace?**
   - ¿Hay diferencia en el proceso de carga?
   - ¿Los plugins `@local` son tratados diferente?

## Archivos Clave para Examinar

```bash
# Plugin structure
ls -la ~/.claude/plugins/context-memory/
cat ~/.claude/plugins/context-memory/.claude-plugin/plugin.json
cat ~/.claude/plugins/context-memory/hooks/hooks.json

# Compare con working plugin
ls -la ~/.claude/plugins/cache/claude-plugins-official/hookify/*/hooks/
cat ~/.claude/plugins/cache/claude-plugins-official/hookify/*/hooks/hooks.json

# Compare con local plugin
ls -la ~/.claude/plugins/test-hook/
cat ~/.claude/plugins/test-hook/hooks/hooks.json

# Registration
cat ~/.claude/plugins/installed_plugins.json | grep -A5 context-memory
cat ~/.claude/plugins/installed_plugins.json | grep -A5 test-hook
cat ~/.claude/plugins/installed_plugins.json | grep -A5 hookify
```

## Output Esperado

Por favor, proporciona:

1. **Diagnóstico principal**: ¿Cuál es la causa raíz de que los hooks no se disparen?

2. **Comparación**: Tabla comparando context-memory vs hookify vs test-hook

3. **Solución propuesta**: Qué cambios específicos se necesitan hacer

4. **Verificación**: Cómo probar que la solución funciona

---

**IMPORTANTE**: Usa superpowers:systematic-debugging para el análisis. NO propongas soluciones sin investigar primero.
