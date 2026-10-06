# References — 외부 기술 근거와 범위

확인일: **2026-10-06**. 아래는 공식 문서에서 확인한 프로토콜·저장·관찰 제약입니다. Locus의 데이터 모델·권한 설계·구현 우선순위는 이 프로젝트의 제안이며, 해당 표준이 요구하는 Locus 전용 기능은 아닙니다.

MCP 문서는 명시적인 **2025-11-25 specification 경로를 검토 기준**으로 삼았습니다. 이를 현재 모든 host가 지원한다거나 최신판이라고 선언하지 않습니다. 구현 시 SDK 버전, 협상한 protocol version, host 버전을 기록해야 합니다.

<a id="s1"></a>
## S1. MCP Architecture

https://modelcontextprotocol.io/specification/2025-11-25/architecture

Host가 client 연결·권한·context aggregation을 관리하며, server는 필요한 context만 받는 구조입니다. 전체 대화 이력을 server가 자동으로 읽는 계약이 아니고, capability는 협상됩니다. Locus의 hook·자동 주입·제품별 연동을 별도 검증 대상으로 둔 근거입니다.

<a id="s2"></a>
## S2. MCP Transports

https://modelcontextprotocol.io/specification/2025-11-25/basic/transports

Stdio는 client가 server subprocess를 시작합니다. Streamable HTTP는 독립 server process의 연결 방식을 제공합니다. HTTP 구성에는 Origin 검사, 로컬 bind, 인증 관련 보안 고려가 있습니다. Locus의 단일 daemon + stdio adapter는 이 제약에 대한 **설계 선택**입니다.

<a id="s3"></a>
## S3. MCP Tools

https://modelcontextprotocol.io/specification/2025-11-25/server/tools

도구 목록·호출, input/output schema와 구조화 결과를 정의합니다. Tool annotations는 신뢰 근거 없이 안전성 보증으로 취급하지 않습니다. Locus는 MCP 도구 표면과 자체 권한 enforcement를 분리합니다.

<a id="s4"></a>
## S4. MCP Authorization / Security Best Practices

https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization

https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices

HTTP 인증과 stdio credential 취급을 구분하고, 토큰 전달·audience·proxy의 confused deputy 위험을 다룹니다. Locus가 원천 서비스 token을 Agent에게 전달하거나 다른 용도의 token을 그대로 수용하지 않도록 한 참고 근거입니다. 전체 보안 적합성 인증을 뜻하지 않습니다.

<a id="s5"></a>
## S5. MCP Roots

https://modelcontextprotocol.io/specification/2025-11-25/client/roots

Roots는 파일 접근 범위를 전달하는 기능이며 client/server의 경로 검증·접근 통제가 별도로 기술되어 있습니다. Locus는 roots 목록 자체를 OS sandbox로 간주하지 않고, 자체 root policy와 파일 접근 검증을 요구합니다.

<a id="s6"></a>
## S6. SQLite WAL / Backup

https://sqlite.org/wal.html

https://sqlite.org/backup.html

WAL의 reader/writer 동작과 단일 writer 제약, 일관된 백업을 위한 Backup API를 참고했습니다. Locus는 단일 write 경로를 두고, 실행 중 DB 파일 하나를 임의 복사하는 대신 일관된 snapshot을 생성하는 정책을 채택합니다.

<a id="s7"></a>
## S7. Apple File System Events

https://developer.apple.com/library/archive/documentation/Darwin/Conceptual/FSEvents_ProgGuide/UsingtheFSEventsFramework/UsingtheFSEventsFramework.html

Apple의 archived FSEvents 문서는 event coalescing·dropped event와 재스캔 필요성을 설명합니다. 최신 SDK의 완전한 구현 가이드로 쓰지 않으며, watcher를 완전한 이력 원장 대신 재확인 hint로 취급한 근거입니다. 실제 macOS API 선택은 구현 시 다시 검증합니다.

## 입력 문서와 변경 추적

프로젝트 요구의 직접 근거는 이 대화의 `Locus v0.1 — Core Architecture` 및 사용자가 제공한 Personal GC Context Snapshot입니다. 기존 합의와 새 보강의 차이는 [Architecture Review](architecture-review.md)에 기록했습니다. 개인 대화 전문, 계정별 정보, 실제 개인 파일 경로는 공개 저장소에 복제하지 않았습니다.
