# Agentic Report Integration

Phase 3B.3 extends deterministic HTML reports with an Agentic Plan Execution
Evidence section when plan execution audit files are present in the run
directory.

The report includes:

- application mode
- approved specification revision
- strategy plan ID
- plan execution status
- step executions
- observations
- validation gate results
- next-action recommendations

Manual runs and non-agentic runs still generate reports normally. They do not
claim plan approval or plan-step execution.
