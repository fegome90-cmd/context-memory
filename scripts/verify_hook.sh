#!/bin/bash
# Verification script for context-memory plugin hooks
# Run this in a Claude Code session to test if hooks are working

echo "=== Context Memory Hook Verification ==="
echo ""

# Check debug log
echo "1. Debug log (/tmp/cm_hook_debug.log):"
if [ -f /tmp/cm_hook_debug.log ]; then
    echo "   ✅ EXISTS"
    echo "   Lines: $(wc -l < /tmp/cm_hook_debug.log)"
    echo "   Last 3 entries:"
    tail -3 /tmp/cm_hook_debug.log | sed 's/^/   /'
else
    echo "   ❌ NOT FOUND (hook not called yet)"
fi
echo ""

# Check current.jsonl
echo "2. Event log (.claude/context_memory/sessions/current.jsonl):"
if [ -f .claude/context_memory/sessions/current.jsonl ]; then
    LINES=$(wc -l < .claude/context_memory/sessions/current.jsonl)
    echo "   ✅ EXISTS"
    echo "   Events captured: $LINES"
    if [ "$LINES" -gt 0 ]; then
        echo "   Last event:"
        tail -1 .claude/context_memory/sessions/current.jsonl | sed 's/^/   /'
    fi
else
    echo "   ❌ NOT FOUND"
fi
echo ""

# Check plugin registration
echo "3. Plugin registration:"
if grep -q "context-memory@local-marketplace" ~/.claude/plugins/installed_plugins.json 2>/dev/null; then
    echo "   ✅ REGISTERED as context-memory@local-marketplace"
    grep -A3 "context-memory@local-marketplace" ~/.claude/plugins/installed_plugins.json | sed 's/^/   /'
else
    echo "   ⚠️  NOT FOUND in installed_plugins.json"
fi
echo ""

# Summary
echo "=== Summary ==="
if [ -f /tmp/cm_hook_debug.log ] && [ -f .claude/context_memory/sessions/current.jsonl ]; then
    HOOK_CALLS=$(wc -l < /tmp/cm_hook_debug.log)
    EVENTS=$(wc -l < .claude/context_memory/sessions/current.jsonl)
    if [ "$HOOK_CALLS" -gt 0 ] && [ "$EVENTS" -gt 0 ]; then
        echo "✅ PLUGIN WORKING - Hooks are firing!"
    else
        echo "⚠️  PLUGIN REGISTERED but no activity yet"
        echo "   Try reading a file to trigger the hook"
    fi
else
    echo "❌ PLUGIN NOT ACTIVE - Hooks not firing"
    echo "   This session may have started before plugin registration"
    echo "   Try starting a NEW Claude Code session"
fi
