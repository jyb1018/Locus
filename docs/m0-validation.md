# M0 — 검증 기록

## 구현 시점의 확인 (2026-10-06)

| 항목 | 결과 | 정확한 범위 |
|---|---|---|
| Python 문법 검사 | 통과 | `python -m compileall -q src` |
| Core + Unix socket 자동 테스트 | **50 passed** | Linux / Python 3.13.5, 합성 fixture |
| 공식 MCP SDK subprocess 테스트 | **로컬에서 1개 모듈 skip** | 실행 컨테이너에 SDK가 없고 외부 DNS/패키지 다운로드가 제한되었습니다. 통과로 세지 않습니다. |
| 두 IPC 클라이언트 smoke | **PASS** | 아래 8개 검사를 실제 daemon process에 수행했습니다. MCP 또는 실제 AI 호스트 검증이라고 부르지 않습니다. |
| GitHub Actions | workflow 추가 | Linux 3.11, macOS 3.13에서 SDK 설치 후 전체 테스트와 stdio demo 실행. 실제 실행 결과는 PR Checks를 확인합니다. |
| 실제 제품 호스트 2개 | **미검증** | 머지 후 아래 표를 채워야 합니다. |

CI의 `LOCUS_REQUIRE_MCP=1`은 SDK 검사 누락을 실패로 처리합니다. CI가 통과했다는 문구는 관찰된 실행 결과 없이 이 문서에 미리 기록하지 않습니다.

IPC smoke에서 확인한 항목:

1. 같은 idempotency key 재시도에 같은 receipt, 한 번의 저장.
2. A의 note를 B가 동일한 Claim ID와 provenance로 읽음.
3. A 전용 predicate가 B의 값·개수·snapshot에 나타나지 않음.
4. 권한 밖 Entity가 직접 ID 조회에서도 거부됨.
5. 배타적인 두 상태 보고가 `CONFLICTED`로 함께 보존됨.
6. daemon 강제 종료 후 동일 DB 복구 및 같은 클라이언트 재연결.
7. read-only grant 변경 후 직접 호출도 쓰기 거부.
8. credential 철회 후 기존 클라이언트의 읽기 거부.

추가 테스트는 원자적 rollback, stale revision, 다른 Agent의 Claim 대체 거부, private evidence 공개 범위, 동시 daemon 방지, malformed/oversized frame, 파일 권한, token symlink, secret 비노출, 스키마 버전 불일치, 입력 및 출력 예산을 포함합니다. 이것은 독립 보안 감사나 악성 같은-UID 프로세스 격리 검증이 아닙니다.

## 실제 호스트 검증 표 — 머지 후 작성

| 항목 | Host A | Host B |
|---|---|---|
| 제품명 및 정확한 버전 | 미기록 | 미기록 |
| 운영체제/아키텍처 | 미기록 | 미기록 |
| 로컬 stdio 지원 및 설정 경로 | 미검증 | 미검증 |
| 사용한 Principal | client-a | client-b |
| `tools/list`, 조회, Claim 기록 | 미검증 | 미검증 |
| 상대 호스트 Claim 이어받기 | 미검증 | 미검증 |
| private predicate 차단 | A만 허용 예정 | 미검증 |
| daemon 재시작 후 동일 세션 재연결 | 미검증 | 미검증 |
| grant/credential 철회 반영 | 미검증 | 미검증 |
| LLM의 수동/자발적 도구 호출 방식 | 미기록 | 미기록 |
| 오류와 재현 절차 | 미기록 | 미기록 |

같은 제품의 세션 두 개만 사용했다면 그 사실을 기록합니다. 그것을 서로 다른 제품 두 개의 호환성 증명으로 격상하지 않습니다. Dot/Muse의 대화 hook·자동 context 주입·원격 bridge는 이 PR의 검사 대상이 아닙니다.

## 아직 완료가 아닌 것

이 PR은 **M0 구현을 리뷰하고 실제 호스트에서 시험할 수 있는 상태**를 만드는 작업입니다. 전체 M0의 실제 제품 통합 수용 조건, 전체 M1, Filesystem/GC, 공개 remote service, 장기 보존·purge, 실제 source freshness는 후속입니다. 새로운 기능을 시작하기 전에 runbook의 두 호스트 시나리오를 먼저 수행합니다.
