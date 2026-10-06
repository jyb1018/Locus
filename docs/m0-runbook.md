# M0 — 실행 및 머지 후 호스트 검증

이 문서는 **현재 실행 가능한 spike**의 범위를 설명합니다. v0.1.1 전체 설계의 구현 완료를 뜻하지 않습니다. 실제 파일·메일을 수집하지 않고 생성한 가상 프로젝트만 사용합니다.

## 1. 실행 환경

Python 3.11 이상, macOS 또는 Linux의 로컬 환경을 대상으로 합니다. Windows named pipe, 원격 MCP/HTTP, 클라우드 bridge는 없습니다. Core는 표준 라이브러리만 사용하고, MCP 어댑터는 공식 Python SDK `mcp==1.29.0`을 별도로 설치합니다. 선택 이유와 한계는 [결정 기록](decisions/0001-m0-execution-boundary.md)을 참조하십시오.

저장소 루트에서 실행합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m locus.demo
```

마지막 명령은 임시 디렉터리를 만들고 **daemon 1개 + 공식 SDK 클라이언트 2개 + stdio 어댑터 2개**를 실행합니다. Claim 공유, 비공개 범위 차단, 충돌 보존, 강제 종료 후 복구, 권한 변경과 credential 철회를 검사한 뒤 모두 종료합니다. 자동으로 만들어진 가상 데이터만 정리합니다. 실제 사용자의 `~/.locus-m0`는 건드리지 않습니다.

`PASS`는 SDK/transport 검사 통과입니다. **Codex·Dot·Muse 등 실제 제품 두 개의 통합 성공은 아닙니다.** 결과에 `real_ai_host_integration: NOT_TESTED`가 함께 출력됩니다.

SDK 없는 오프라인 환경에서는 다음으로 **Core/IPC만** 확인할 수 있습니다. MCP 테스트로 바꿔 부르지 않습니다.

```bash
PYTHONPATH=src python3 -m locus.demo --transport ipc
PYTHONPATH=src python3 -m pytest -q
```

SDK가 없으면 SDK 테스트 모듈이 명시적으로 skip됩니다. CI는 `LOCUS_REQUIRE_MCP=1`을 설정하므로 SDK 누락을 성공으로 처리하지 않습니다.

## 2. 실제 호스트에 연결할 데이터 준비

처음 한 번만 실행합니다. 이미 데이터가 있는 디렉터리는 덮어쓰지 않습니다.

```bash
.venv/bin/python -m locus init-demo
```

기본 위치는 `~/.locus-m0`입니다. 다음이 만들어집니다.

```text
~/.locus-m0/
  state.sqlite3       # daemon이 소유하는 SQLite
  owner.token         # 로컬 관리 전용, AI 호스트에 제공 금지
  client-a.token      # 호스트 A 전용 credential
  client-b.token      # 호스트 B 전용 credential
  fixture.json        # 합성 Entity/Principal ID, token 파일 경로 (token 값 없음)
  daemon.lock
```

디렉터리는 `0700`, 파일은 `0600`입니다. **token 내용은 채팅·Git·스크린샷에 올리지 마십시오.** `init-demo`는 secret 값이 아니라 ID와 경로만 출력합니다. 다른 위치를 쓸 때는 모든 명령에 동일한 `--home /짧은/경로`를 지정하거나 `LOCUS_HOME`을 사용하십시오. Unix socket 경로는 100바이트 이하로 제한합니다.

별도 터미널에서 daemon을 실행하고 켜둡니다.

```bash
.venv/bin/python -m locus serve
```

자동 설치되는 백그라운드 서비스는 없습니다. `Ctrl-C`로 종료합니다. 두 번째 daemon은 기존 socket을 지우지 않고 `DAEMON_RUNNING`으로 실패합니다. 비정상 종료 후 같은 명령으로 다시 실행하면 기존 DB와 credential을 사용합니다.

## 3. 호스트 A/B 설정

각 호스트에 넣을 **generic MCP 설정**을 생성합니다.

```bash
.venv/bin/python -m locus config --client client-a
.venv/bin/python -m locus config --client client-b
```

출력에는 현재 Python 실행 파일의 **절대 경로**, 동일한 state home, 서로 다른 token 파일 경로가 들어갑니다. 각 호스트의 MCP 설정 형식에 맞춰 `command`와 `args`를 등록하십시오. A에 `client-a`, B에 `client-b`를 사용해야 권한 분리를 검사할 수 있습니다. 같은 credential을 두 군데 복사하면 이 검증은 성립하지 않습니다.

Codex 및 다른 로컬 stdio MCP 호스트를 후보로 삼을 수 있지만, 설치된 제품·버전·설정 방식은 실제로 확인해야 합니다. generic `mcpServers` JSON을 모든 제품이 그대로 읽는다는 뜻은 아닙니다. Hosted-only Dot/Muse가 로컬 stdio를 직접 지원한다고 가정하지 않습니다.

## 4. 수동 검증 시나리오

`fixture.json`의 `entities.shared` ID를 사용합니다. 아래 `<SHARED_ENTITY_ID>`는 실제 출력된 ID로 바꾸십시오.

A의 새 세션에서 다음 도구 호출을 요청합니다.

```json
{
  "subject_id": "<SHARED_ENTITY_ID>",
  "predicate": "locus.note",
  "value": "M0 검증: 다음 작업은 두 호스트 간 상태 복구 확인입니다.",
  "idempotency_key": "manual-handoff-001"
}
```

도구는 `locus_record_claim`입니다. 같은 호출을 재시도할 때는 **같은 idempotency key와 같은 입력**을 사용합니다. 내용을 바꾼 새 Claim은 새 key를 사용합니다.

B의 새 대화에서 `locus_get_entity`에 같은 Entity ID를 넣습니다. A가 남긴 값, `claim_id`, `created_by`, `AGENT_INFERRED`가 보여야 합니다. B가 A의 채팅 기록을 복사받지 않았는지도 확인합니다.

A가 동일한 Entity에 `locus.private.note`로 별도 note를 남기면 B의 조회에는 predicate·값·개수가 나오지 않아야 합니다. B가 `entities.private` ID를 직접 요청해도 존재하지 않는 ID와 같은 `NOT_FOUND`가 나와야 합니다. A 전용 note가 변해도 B의 `snapshot_token`은 바뀌지 않아야 합니다.

daemon을 중지하고 같은 home으로 다시 시작합니다. 호스트 A/B의 어댑터는 매 호출마다 연결하므로 기존 세션에서도 다시 읽을 수 있어야 합니다. 중지 중 호출은 명시적인 오류여야 하며, 빈 상태나 성공 응답이어서는 안 됩니다.

마지막으로 B의 credential 철회를 확인합니다. 이 작업은 B의 이후 접근을 중단하므로 검증 마지막에 합니다.

```bash
.venv/bin/python -m locus owner revoke '<CLIENT_B_PRINCIPAL_ID>'
```

B의 기존 세션에서도 다음 조회가 `UNAUTHENTICATED`로 거부되어야 합니다. 철회한 credential을 재활성화하는 명령은 M0에 없습니다. 재시험에는 새로운 `--home`으로 별도 fixture를 만드십시오. 기존 디렉터리를 `init-demo`가 덮어쓰지 않습니다.

## 5. 현재 도구와 데이터 계약

| 도구 | 입력 | 동작 |
|---|---|---|
| `locus_search` | `query?`, `limit?` (1–20) | 허용된 Entity 이름/ID만 검색합니다. Claim 본문 전체검색·cursor는 없습니다. 잘린 경우 `truncated`가 표시됩니다. |
| `locus_get_entity` | `entity_id`, `predicate?` | 허용된 predicate별 현재 보고와 근거를 제공합니다. predicate를 지정해 응답을 좁힐 수 있습니다. |
| `locus_record_claim` | subject/predicate/value/key, evidence 및 revision 선택 | 일반 Agent 보고만 저장합니다. `record_event`·원천 mutation·임의 SQL은 없습니다. |

등록된 predicate는 `locus.note`, `locus.private.note`, `locus.project.implementation_status`뿐입니다. private라는 이름 자체가 ACL은 아니며 실제 grant가 접근을 결정합니다. 기본 fixture에서는 A만 private note를 읽고 씁니다.

상태 값은 `not_started / in_progress / blocked / reported_complete`이며 읽을 수 있는 동일 Entity의 Evidence Claim이 필요합니다. 서로 다른 값의 활성 보고가 공존하면 `CONFLICTED`이고 자동 last-writer-wins는 없습니다. 이것은 사용자 의도인 “중단/재개”를 변경하지 않습니다. Note는 근거 없는 보고를 허용하지만 authoritative fact로 승격되지 않습니다.

자기 Claim을 명시적으로 대체할 때만 `supersedes_claim_id`와 **해당 predicate의** `expected_subject_revision`을 함께 제공합니다. 다른 Principal의 revision이나 다른 Agent의 Claim은 사용할 수 없습니다. 저장 성공은 진실 검증 성공이 아닙니다.

M0는 가상 fixture에 한정하므로 predicate별 history는 **16개**, value는 **직렬화 UTF-8 512바이트**, evidence는 **8개**, request는 **32 KiB**, Core response는 **48 KiB**로 제한합니다. SDK는 structured/text 두 표현을 사용할 수 있습니다. 너무 큰 조회는 `RESPONSE_TOO_LARGE`로 실패하며 조용히 일부 주장만 반영하지 않습니다. `predicate`로 범위를 좁히십시오. 대량 데이터용 pagination/retention은 후속입니다.

## 6. 보안 및 미구현 경계

이것은 **같은 OS 사용자로 실행하는 악성 코드의 sandbox가 아닙니다.** 같은 UID에서 shell이나 파일 읽기 도구를 가진 AI는 credential/DB에 직접 접근할 수 있습니다. 그러한 호스트에 대한 강제 격리는 별도 OS 사용자·sandbox 등의 후속 설계가 필요합니다. M0의 권한 검사는 Locus API를 통한 요청 범위에서만 성립합니다.

State DB는 애플리케이션 수준으로 암호화하지 않습니다. 원격 endpoint, OS keychain, 키 회전, export/purge, GC·Filesystem Provider, Claim 만료·철회, 범용 스키마·Module SDK, 문서 파서는 구현하지 않았습니다. 실제 비밀이나 개인정보를 넣지 마십시오. 호스트가 조회 결과를 외부 모델에 보내는 것 또한 별도의 데이터 반출입니다.

M0는 MCP SDK의 transport에 의존하며 임의 크기 입력에 대한 호스트 프로세스 전체의 메모리 격리를 보장하지 않습니다. IPC로 전달할 요청과 Core가 내보내는 응답의 크기를 제한합니다. daemon은 인증을 매번 확인하며 조회 cache를 두지 않습니다.

## 7. 결과 기록

머지 후 테스트 시 [검증 기록](m0-validation.md)의 실제 호스트 표에 제품명·버전·transport·호출 권한·성공/실패·오류 재현을 기록합니다. 실제 두 호스트에서 성공하기 전까지 문서상 M0는 **Core/transport spike 및 호스트 검증 대기**입니다.
