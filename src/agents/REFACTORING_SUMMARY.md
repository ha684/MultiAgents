# Refactoring Summary: ChatGPT-Style Two-Phase Thinking Graph

## Overview

Refactored `ThinkingGraph` to use a two-phase approach similar to ChatGPT's iterative thinking process, where each iteration has:
1. **Phase Planning**: Decide phase title and action type
2. **Action Execution**: Execute the planned action (reasoning or tool usage)

## Changes Made

### 1. New Agents

#### `src/agents/basic/phase_agent.py` (NEW)
- **Purpose**: Phase planning agent that decides what to do next
- **Input**: Current state (learnings, knowledge, execution history, missing aspects)
- **Output**: 
  - `phase_title`: Descriptive title for the phase (e.g., "Looking up renewable energy reports")
  - `next_action`: Either "reason_only" or "use_tool"
- **Examples of Phase Titles**:
  - "Looking up renewable energy reports"
  - "Analyzing cloud platform cost-performance tradeoffs"
  - "Structuring renewable energy adoption essay"
  - "Browsing international renewable energy policies"

#### `src/agents/basic/action_execution_agent.py` (NEW)
- **Purpose**: Execute the action decided by phase agent
- **Two Modes**:
  1. **reason_only**: Generate internal reasoning/analysis
     - Output: `{"reasoning": "deep analytical content..."}`
  2. **use_tool**: Select subgraph and generate query
     - Output: `{"subgraph": "web_search", "query": "specific search query"}`

### 2. Updated Files

#### `src/agents/graph/thinking_graph.py`
- **New Flow**:
  ```
  phase_planning → action_execution → [route] → execute/reason → evaluate → continue/synthesize
  ```
- **Replaced Nodes**:
  - Old: `generate_direction_node`
  - New: `phase_planning_node` + `action_execution_node`
- **Benefits**:
  - Clearer separation of concerns (what to do vs how to do it)
  - More transparent reasoning process
  - Better phase visibility (like ChatGPT)

#### `src/domain/entities/state.py`
- **Added Fields to ThinkingState**:
  - `phase_title`: Current phase description
  - `next_action`: Action type ("reason_only" or "use_tool")
  - `_execution_failed`: Flag for execution failures
  - `_failure_reason`: Reason for failure

#### `src/agents/prompts/agent_prompts.py`
- **Added Three New Prompts**:
  1. `PHASE_PLANNING_PROMPT`: Guide for phase planning
  2. `REASONING_EXECUTION_PROMPT`: Guide for generating reasoning
  3. `TOOL_EXECUTION_PROMPT`: Guide for tool selection and query generation
- **Kept Legacy**: `DIRECTION_GENERATION_PROMPT` for backward compatibility (used by NormalGraph)

#### `src/agents/basic/__init__.py`
- **Added Exports**:
  - `phase_agent`
  - `action_execution_agent`
- **Kept**: `direction_generation_agent` for backward compatibility

### 3. Files NOT Changed

#### `src/agents/graph/normal_graph.py`
- Still uses `direction_generation_agent`
- **Reason**: NormalGraph is a fast path with single-shot execution
- No need for ChatGPT-style iteration phases

#### `src/agents/basic/direction_generation_agent.py`
- Kept unchanged for backward compatibility
- Still used by NormalGraph

## Flow Comparison

### Old Flow (Single Agent)
```
generate_direction (all-in-one)
  ↓
[decide action route]
  ↓
execute/reason → evaluate → continue/synthesize
```

### New Flow (Two-Phase)
```
phase_planning (decide what to do)
  ↓
action_execution (execute the action)
  ↓
[decide action route]
  ↓
execute/reason → evaluate → continue/synthesize
```

## Example Iteration Sequence

### Iteration 1: Data Gathering
- **Phase Planning**: 
  - Phase Title: "Looking up renewable energy reports"
  - Next Action: "use_tool"
- **Action Execution**: 
  - Subgraph: "web_search"
  - Query: "IEA IRENA renewable energy global adoption report 2024 2025"

### Iteration 2: Analysis
- **Phase Planning**: 
  - Phase Title: "Analyzing renewable energy cost trends"
  - Next Action: "reason_only"
- **Action Execution**: 
  - Reasoning: "With data from IEA and IRENA, I can analyze... [deep analysis]"

### Iteration 3: More Data
- **Phase Planning**: 
  - Phase Title: "Browsing international renewable energy policies"
  - Next Action: "use_tool"
- **Action Execution**: 
  - Subgraph: "web_search"
  - Query: "Paris Agreement renewable energy targets EU Green Deal policy"

### Iteration 4: Structuring
- **Phase Planning**: 
  - Phase Title: "Structuring renewable energy adoption essay"
  - Next Action: "reason_only"
- **Action Execution**: 
  - Reasoning: "To structure this systematically... [outline and framework]"

## Benefits of Refactoring

1. **Clearer Intent**: Phase titles make it transparent what the agent is trying to do
2. **Better Separation**: Decision (what) separated from execution (how)
3. **ChatGPT-like Experience**: Users can see clear phase progression
4. **Easier Debugging**: Can track exactly what the agent decided and why
5. **More Maintainable**: Each agent has a single, clear responsibility

## Migration Notes

### For ThinkingGraph Users
- **No API changes** - ThinkingGraph still accepts same inputs and returns same outputs
- **State fields added** - New fields in state, but backward compatible
- **Logging enhanced** - Better visibility into phase planning

### For NormalGraph Users
- **No changes** - Continues to use original `direction_generation_agent`

## Testing

Recommended tests:
1. Run existing ThinkingGraph tests to ensure backward compatibility
2. Check phase titles are generated correctly
3. Verify action execution splits correctly between reasoning and tool use
4. Test failure recovery (consecutive failures, repeated subgraph failures)

## Future Enhancements

Potential improvements:
1. Add phase progress indicator (e.g., "Phase 1 of estimated 5")
2. Stream phase titles to frontend for real-time visibility
3. Add phase time tracking for performance monitoring
4. Implement phase result caching for similar queries

