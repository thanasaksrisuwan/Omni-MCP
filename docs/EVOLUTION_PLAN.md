# SRS: Omni-MCP: The Core Protocol (Evolution Plan)
**Version:** 2.0.0 (The Upgrade)  
**Status:** Draft / Strategic Planning  
**Concept:** From "Static Auditor" to "Secure Execution Engine"

---

## 1. Executive Summary

ระบบ **Omni-MCP: The Core Protocol** คือการวิวัฒนาการจากระบบตรวจสอบข้อมูล (Static Analysis) ไปสู่ระบบที่สามารถ **"ลงมือทำ" (Execution)** ได้อย่างอิสระแต่ปลอดภัย 100% โดยการนำขีดความสามารถของ `mcp_bmntogodev` มารีแบรนด์และหลอมรวมเข้ากับกฎเหล็กของ Omni-MCP เดิม

เป้าหมายสูงสุดคือ: **"AI can execute, but AI cannot violate."**

---

## 2. Architectural Evolution

| Layer | Omni-MCP 1.0 (Static) | Omni-MCP 2.0 (Core Protocol) |
| :--- | :--- | :--- |
| **Input** | AI Reads Manifests | AI Queries Semantic Bridge |
| **Logic** | Manual Validator Call | Auto-Enforced Validation Hooks |
| **Writing** | Standard `write_file` | `omni.scribe` (Validation-Locked) |
| **Runtime** | No Runtime Visibility | `omni.vision` (Manifest-Linked Trace) |
| **Testing** | Manual Scripts | `omni.vault` (Auto-Sandbox/Invariants) |

---

## 3. Rebranded Modules & Features

### 3.1 Omni-Scribe (The Secure Writer)
*Evolution of `safe_edit_batch` + `pre_write_guard`*
- **Purpose:** ป้องกันการเขียนโค้ดที่ละเมิดกฎโปรเจกต์แบบ Real-time
- **Features:**
    - **Atomic Lock:** ทุกการแก้ไขไฟล์จะถูกส่งไปรัน Validator (Frontend/Backend) ก่อนบันทึกลงดิสก์
    - **Self-Healing:** หาก Validator พบจุดผิดที่แก้ไขได้ง่าย (เช่น Import path ผิด) ระบบจะแนะนำโค้ดที่ถูกต้องให้ AI ทันที
    - **Convention Guard:** บล็อกการใช้ `session.commit()` ในชั้น Service หรือการใช้ Inline Styles ที่ผิดกฎ CSS Tokens

### 3.2 Omni-Vision (Semantic Trace)
*Evolution of `trace_request` + `runtime_xray`*
- **Purpose:** ให้ AI เห็น Flow การทำงานจริงที่เชื่อมโยงกับ Manifests
- **Features:**
    - **Route-to-Model Mapping:** เมื่อ Trace API จะดึงข้อมูลจาก `routes.json` มาจับคู่กับ `sqlalchemy-models.json`
    - **Session Ownership Trace:** แสดงจุดเปิด/ปิด Transaction จริงใน Runtime เพื่อเปรียบเทียบกับ `transaction-boundaries.json`
    - **UI Surface Mapping:** แสดง Component Tree และ Props ที่ถูก Render จริงบนหน้าจอ

### 3.3 Omni-Vault (Transactional Sandbox)
*Evolution of `db_fixture_tx` + `reservation_safety`*
- **Purpose:** พื้นที่ทดลองรันโค้ดที่การันตีว่าข้อมูลจริงจะไม่พัง
- **Features:**
    - **Invariant Watchdog:** ตรวจสอบกฎการจอง (INV001-007) ทุกครั้งที่มีการ Query/Update ใน Sandbox
    - **Auto-Rollback Environment:** รันทุกคำสั่งของ AI ภายใต้ Transaction ที่จะ Rollback อัตโนมัติเสมอ (Safe Exploration)
    - **State-aware Mocking:** สร้างข้อมูลจำลองตามสถานะใน `state-machines.json` สำหรับการทดสอบ logic

### 3.4 Omni-Bridge (Context Orchestrator)
*Evolution of `context_pack` + `impact_analysis`*
- **Purpose:** จัดการ Context ให้ AI อย่างแม่นยำและประหยัด Token
- **Features:**
    - **Semantic Bundling:** มัดรวมไฟล์ที่เกี่ยวข้องตามความสัมพันธ์ใน Manifest (เช่น แก้ Model -> ดึง Validator และ Route ที่ใช้ Model นั้นมาด้วย)
    - **Impact Scorer:** คำนวณความเสี่ยงของการแก้ไขโค้ดในจุดต่างๆ โดยอ้างอิงจาก `usages.json`

---

## 4. Implementation Roadmap

### Phase 1: The Foundation (Omni-Bridge & Scribe)
- [ ] Implement `omni.bridge_pack_context` โดยใช้ข้อมูลจาก `.backend-ai/*.json`
- [ ] Implement `omni.scribe_write_file` ที่มี Hook รัน `backend_reservation_safety.py` ในตัว

### Phase 2: Runtime Intelligence (Omni-Vision)
- [ ] พัฒนา FastAPI Middleware สำหรับส่ง Trace Data (Method, Session, Transaction)
- [ ] สร้าง Tool `omni.vision_trace_route` เพื่อแสดงผลการทำงานแบบ Semantic

### Phase 3: The Fortress (Omni-Vault)
- [ ] พัฒนา SQLAlchemy Wrapper สำหรับ Transactional Sandbox
- [ ] สร้างระบบตรวจสอบ Invariants แบบ Dynamic ในขณะรัน Test

---

## 5. Task Ledger (Omni-MCP Evolution)

| Task ID | Component | Description | Status |
| :--- | :--- | :--- | :--- |
| CORE-001 | Omni-Bridge | สร้างสคริปต์รวม Context จากความสัมพันธ์ใน Manifests | `not_started` |
| CORE-002 | Omni-Scribe | แก้ไข `mcp_server.py` ให้ใช้ Secure Writing Flow | `not_started` |
| CORE-003 | Omni-Vision | สร้างตัวดึงข้อมูล Runtime จาก FastAPI เข้าสู่ระบบ MCP | `not_started` |
| CORE-004 | Omni-Vault | สร้างระบบ Auto-Rollback Test Environment สำหรับ SQLAlchemy | `not_started` |
| CORE-005 | Rebranding | อัปเดต `AGENTS.md` และเครื่องมือทั้งหมดให้ใช้ชื่อแบรนด์ใหม่ | `not_started` |

---

---

## 7. Version 3.0: The Sentience Upgrade (The Buffs)
**Concept:** From "Secure Engine" to "Intelligent Engineering Partner"

### 7.1 Omni-Oracle (Contextual Memory)
- **Goal:** ป้องกัน AI ถามซ้ำและให้บทเรียนจากการตัดสินใจในอดีต
- **Feature:** Decision Log System (Markdown/JSON) + Vector Indexing readiness.

### 7.2 Omni-Medic (Self-Healing Hooks)
- **Goal:** ลดการแก้โค้ดซ้ำซ้อนโดยให้ระบบแนะนำการแก้ไข (Auto-fix) ทันทีที่พบ Error
- **Feature:** Code Transformation suggestions based on validation failure patterns.

### 7.3 Omni-Ghost (Shadow Execution)
- **Goal:** เพิ่มความแม่นยำในการเทสด้วยข้อมูลจำลองที่ใกล้เคียงความจริงที่สุด
- **Feature:** Anonymized data simulation in Transactional Sandbox.

### 7.4 Omni-Guardian (Adversarial Validation)
- **Goal:** ป้องกัน AI เขียนโค้ด "ทางลัด" ที่แค่ผ่านด่านตรวจแต่ไม่ปลอดภัยจริง
- **Feature:** Secondary agent logic for stress-testing code in Sandbox.

### 7.5 Omni-Aura (Visual/UX Semantics)
- **Goal:** ให้ AI เข้าใจสุนทรียภาพและความง่ายในการใช้งานของ UI
- **Feature:** Accessibility & UX semantic analysis integrated into Omni-Vision.
