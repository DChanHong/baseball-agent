# Security Completion Checklist

이 문서는 Step 1~9 보안 개선이 1차 완료 기준을 만족하는지 점검하기 위한 체크리스트다.

## 완료 기준

| 기준 | 상태 | 근거 |
|---|---|---|
| 입력 길이와 기본 형식 검증 | 완료 | `ChatRequest.message`, `session_id`, `user_context` 검증 |
| 시스템 프롬프트 외부 컨텍스트 경계 명시 | 완료 | `app/prompts.py`의 `<security>`, `<rag_policy>`, `<tool_policy>` |
| 내부 지침, API key, 로그 요구 거절 | 완료 | `app/security.py` 거절 정책과 refusal code |
| 세션 히스토리 오염 방지 | 완료 | history 저장 길이 제한, session state 서버 관리 |
| Tool 인자 검증 | 부분 보류 포함 완료 | 적용 완료 Tool은 검증됨. `find_kbo_game` 자연어 날짜 parser 확장은 보류 |
| Tool 에러 메시지 안전화 | 완료 | 외부 API/FAISS/RAG 예외의 사용자 노출 메시지 정리 |
| RAG 출처와 데이터 한계 metadata | 완료 | `source_type`, `source_file`, `trust_level`, `data_limitations` |
| observation과 trace metadata 마스킹 | 완료 | 민감 키/값 패턴 마스킹, 원문 저장 축소 |
| Promptfoo 보안 테스트 | 완료 | JSON 기반 12개 보안 거절 케이스 |
| Gandalf 공격 패턴 수집 구조 | 완료 | `tests/security/gandalf_attack_cases.json` |
| 정상 질문 기본 smoke 확인 | 완료 | `scripts/run_security_smoke.py`의 정상 메시지 비차단 확인 |

## 검증 명령

Promptfoo 설정 생성:

```bash
venv/bin/python scripts/build_promptfoo_config.py
```

LLM/API 호출 없는 smoke 검증:

```bash
venv/bin/python scripts/run_security_smoke.py
```

로컬 API 기준 Promptfoo 검증:

```bash
venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
npx promptfoo eval -c promptfooconfig.yaml
```

## 현재 보안 테스트 입력

보안 거절 테스트의 원본은 `tests/security/gandalf_attack_cases.json`이다. 새 공격 패턴을 발견하면 이 JSON에 추가하고 `scripts/build_promptfoo_config.py`로 Promptfoo 설정을 다시 생성한다.

## 남은 주의사항

- 정상 기능 전체 회귀 테스트는 LLM/API key, 네트워크, 비용 영향을 받으므로 별도 config로 분리하는 것이 좋다.
- `find_kbo_game`의 자연어 날짜 해석은 LLM 판단을 우선한다는 이유로 하드코딩 parser 확장을 보류했다.
- 보안 smoke test는 공격성 입력의 사전 차단과 정상 질문 비차단만 확인한다. 실제 좌석 추천 품질은 별도 Agent 실행 테스트가 필요하다.
