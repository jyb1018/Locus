# ADR 0001 — M0 실행 경계와 임시 기술 선택

- 상태: M0 spike용 채택, 실제 두 AI 호스트 검증 전
- 날짜: 2026-10-06

## 결정

Python 3.11+, SQLite, Unix domain socket, 하나의 foreground `locus serve`를 사용합니다. 공식 MCP Python SDK `mcp==1.29.0`의 low-level stdio server를 얇은 어댑터로 사용합니다. Core/IPC는 표준 라이브러리만으로 검사할 수 있고 SDK는 `mcp` extra로 분리합니다. 이는 자체 MCP 프로토콜을 새로 구현하자는 결정이 아닙니다.

v1.29.0은 유지보수 계열이며 v2가 최신 stable이라는 사실을 구분합니다. 이 spike는 제한된 stdio/tools 연결을 재현하기 위해 문서와 API를 확인한 버전에 정확히 고정합니다. 최신 버전이라는 주장을 하지 않습니다. 실제 호스트에 v2/새 프로토콜이 필요하면 **어댑터와 SDK 검증만** 바꾸며 Core DB나 State 계약을 같이 교체하지 않습니다. 전이 의존성 전체의 lockfile은 아직 없으므로 완전한 설치 재현성을 주장하지 않습니다.

SDK 출처와 확인한 API:

- [공식 v1 유지보수 문서](https://py.sdk.modelcontextprotocol.io/v1/)
- [mcp 1.29.0 배포 정보](https://pypi.org/project/mcp/1.29.0/)
- [고정 버전 low-level Server 구현](https://github.com/modelcontextprotocol/python-sdk/blob/v1.29.0/src/mcp/server/lowlevel/server.py)
- [MCP stdio transport 규격](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

## 실행과 소유권

```text
MCP host A -> stdio adapter A -- restricted credential A --+
                                                         +-> Unix socket -> one daemon -> SQLite
MCP host B -> stdio adapter B -- restricted credential B --+
owner CLI ------------------- separate owner credential --+
```

어댑터는 DB를 열거나 daemon을 자동으로 만들지 않습니다. daemon이 꺼지면 명시적으로 실패합니다. 어댑터는 각 호출에서 다시 연결하므로 daemon 재시작 뒤 재사용할 수 있습니다. daemon은 수명 전체에 OS file lock을 유지합니다. lock 파일을 지워 다른 inode에서 새 lock을 얻는 경쟁 조건을 만들지 않습니다.

단일 event loop가 짧은 동기 SQLite transaction을 직렬화합니다. 이 선택은 작은 synthetic 데이터만 처리하는 M0용입니다. 큰 파일 읽기나 LLM 호출을 transaction에 넣지 않으며, 그런 작업 자체가 현재 없습니다.

## M0와 M1의 관계

기존 계획의 M0는 transport/Principal 연결이고 M1은 Claim·충돌·저장입니다. 이번 spike는 “A의 보고를 B가 읽는다”는 시연을 위해 **작은 M1 subset**까지 포함합니다. 하지만 전체 Event/Claim/Projection 엔진을 구현한 것으로 간주하지 않습니다.

현재 Entity와 Principal은 fixture 초기화에서만 생성합니다. 정확한 Entity+predicate grant, 일반 Agent Claim, 원자적인 journal+receipt, 요청 당시의 projection만 구현합니다. 임의 domain registration, source ingestion, 자동 identity resolution, Module host, provider freshness, projection replay/purge 등은 없습니다. 정책과 응답의 미구현 범위는 runbook에 명시합니다.

## 검증과 한계

동일 프로세스 mock 호출에만 의존하지 않습니다. subprocess daemon과 Unix socket을 통해 두 credential의 공유, 경합, 강제 종료 후 복구, 재연결, 철회를 검사합니다. 공식 SDK 검사는 **실제로 별도 stdio 어댑터 두 개를 시작**하도록 작성합니다. CI에서는 SDK 누락으로 해당 검사를 skip할 수 없습니다.

테스트 클라이언트 두 개는 실제 제품 두 개가 아닙니다. 실제 호스트 matrix를 별도로 남깁니다. macOS/Linux 밖의 지원, 원격 접근, 같은 UID의 악성 코드 격리, AI 모델의 자발적인 도구 호출은 이 결정에 포함하지 않습니다.
