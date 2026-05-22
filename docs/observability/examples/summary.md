# Observability Example Runs

- generated_at: `2026-05-22T01:09:20.288967+00:00`
- FAISS index status: `ready`
- FAISS document count: `239`
- counts by source type: `{'stadium_seat': 213, 'stadium_metadata': 9, 'ticketing_guide': 10, 'logistics_guide': 7}`
- embedding model: `text-embedding-3-small`

## Files

| Case | Run JSON | Tool Calls JSON | Trace ID | Tools | Elapsed | Stop Reason |
|------|----------|-----------------|----------|-------|---------|-------------|
| Normal schedule lookup | `normal_schedule_run.json` | `normal_schedule_tool_calls.json` | `kbo_14a9f81fe6684825b3dfb9cdf9d0dae6` | `find_kbo_game` | `4624ms` | `final_answer` |
| Normal seat recommendation | `normal_seat_recommendation_run.json` | `normal_seat_recommendation_tool_calls.json` | `kbo_7e76285988b8438ba8a72a82c15fbf09` | `find_kbo_game -> get_stadium_info -> get_weather_context -> search_baseball_knowledge -> score_seat_candidates` | `23564ms` | `final_answer` |
| Failure game not found | `failure_game_not_found_run.json` | `failure_game_not_found_tool_calls.json` | `kbo_a14f471470094ad79b513a81a23bf337` | `find_kbo_game` | `3729ms` | `final_answer` |

## Notes

- These files are sanitized examples generated from real local `/chat` executions.
- API keys and local `.env` values are not written to the examples.
- Runtime `logs/` stays ignored; reviewable submission samples live in this docs directory.
- `flow.mmd` contains the high-level observability flow diagram.
