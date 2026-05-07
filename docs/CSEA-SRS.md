# SRS: Controlled Semi-Autonomous Engineering Agent (CSEA)

## 1. Introduction
### 1.1 Purpose
กำหนดมาตรฐานการควบคุมพฤติกรรม AI Agent (Controlled Semi-Autonomous) เพื่อเปลี่ยนจาก "กุมารทองดิจิทัล" ที่พร้อมเผา Repo ให้กลายเป็น "คนงานที่ถูกจำกัดสิทธิ์" โดยเน้นความปลอดภัยของระบบและการตรวจสอบได้ (Traceability)

---

## 2. 3-Layer Control Architecture

| Layer | Implementation | Purpose |
| :--- | :--- | :--- |
| **Protocol** | `AGENTS.md`, `GEMINI.md` | กติกาเชิงจริยธรรมและขั้นตอนการทำงานแบบ Phase-based |
| **Enforcement** | `config.toml`, Sandbox, Shell Wrapper | กำแพงทางเทคนิค (Default Deny) และสิทธิ์การเข้าถึง |
| **Audit Trail** | `.agent/*.md` (Committed) | หลักฐานการตัดสินใจและร่องรอยการทำงานลง Git |

---

## 3. Database & Discovery Safeguards

### 3.1 DB Mutation Protocol
ห้าม Agent ทำการเปลี่ยนแปลงข้อมูล (Mutation) ในโหมด Analyze, Plan หรือ Verify การทำ Write Operation ต้องมี:
1. **Explicit Approval:** มนุษย์กด Next เท่านั้น
2. **SELECT Preview:** แสดงผลลัพธ์ที่จะถูกกระทบก่อนรันจริง
3. **Row-count Estimate:** คาดการณ์จำนวนแถวที่เปลี่ยน
4. **Transaction Strategy:** ต้องมี `BEGIN TRANSACTION` และ Rollback plan
5. **Backup / Checkpoint Confirmation:** ยืนยันจุดคืนสภาพ (Snapshot/Git Checkpoint/Backup)

### 3.2 Bound Discovery
- **Constraint:** การสำรวจ (Discovery) ทั้งการอ่านไฟล์และการรันคำสั่งต้องจำกัดอยู่ภายใน **Git Root** เท่านั้น
- **Rule:** Agent ห้ามอ่านไฟล์นอก Git Root โดยเด็ดขาด เว้นแต่จะได้รับอนุญาตเป็นกรณีพิเศษ

---

## 4. Operational Control Requirements

### 4.1 Phase 0: Intake & Environment Discovery
Agent ต้องสร้างไฟล์ `.agent/environment.local.md` (Ignore) โดยระบุ:
- OS, Shell, Git Root, Runtime Versions, Package Manager, Manifest Files และ Test/Build Commands
- **Constraint:** Read-only เท่านั้น ห้ามแก้ไฟล์อื่น ห้ามต่อ Network และห้ามติดตั้ง Dependency

### 4.2 Discovery Command Allowlist (Default Deny)
อนุญาตเฉพาะคำสั่งเหล่านี้โดยไม่ต้องขอ Approval:
- **Cross-platform:** `git status`, `git diff --stat`, `git rev-parse --show-toplevel`
- **PowerShell:** `Get-Location`, `Get-ChildItem`, `Get-Content`, `Select-String`, `Get-Command`
- **POSIX Shell:** `pwd`, `ls`, `cat`, `grep`, `command -v`, `uname -a`

### 4.3 Working Tree Preflight
ก่อนเข้าสู่ **Patch Mode** Agent ต้องรัน `git status --short` และ `git diff --stat` หากพบการเปลี่ยนแปลงที่ไม่ได้เกิดจากตัวมันเอง (Unexpected changes) ให้หยุดและรายงานทันที

### 4.4 Secret Handling
หากตรวจพบ Secrets, Credentials, Tokens, Private Keys หรือ Production `.env`:
1. **Stop Immediately:** หยุดทำงานและรายงาน
2. **No Leaks:** ห้าม Copy ค่าเหล่านั้นลงใน Artifacts (บันทึกได้เฉพาะ Path และประเภทของความเสี่ยง)
3. **Request Review:** รอการตรวจสอบจากมนุษย์

---

## 5. Phase-Specific Constraints

### 5.1 Analysis & Blueprint (Phase 1-2)
- **Constraint:** ห้ามเขียนโค้ด Logic ลงไฟล์จริง และใช้ MCP Resources (Read-only) เท่านั้น

### 5.2 Verification (Phase 4)
- **Constraint:** **ห้าม Auto-fix** เมื่อ Test/Lint พัง หากพบ Error ให้บันทึก Output ลง `verification.md` และหยุดทำงานเพื่อรอ Approval ในการกลับไป Phase 3 ห้ามเนียนแก้โค้ดเพิ่มในโหมดนี้

---

## 6. Artifact Hygiene & Traceability

### 6.1 Committed vs Ignored
- **Committed:** `.agent/` (README.md, impact-analysis.md, blueprint.md, patch-log.md, verification.md, decisions.md)
- **Ignore:** `.agent/*.local.*`, `environment.md`, `db-schema-snapshot.json`, `secrets*`, `.env*`

### 6.2 Traceability Metadata
ทุก Artifact ที่ Commit ต้องมี: Task ID/Name, Date/Time, Tool Used, Phase, Git Branch และ Related Requirement/SRS Section

---

## 7. Kill Switch Conditions
Agent ต้องหยุดทำงานทันทีเมื่อ:
- พบคำสั่งติด Blacklist (`DROP`, `TRUNCATE`, `migrate:fresh`, `rm -rf /`)
- พบข้อมูลคลุมเครือ (Ambiguous SRS)
- พบความเสี่ยงด้านความปลอดภัย (Secrets/Out-of-bound access)
- Test ล้มเหลวในโหมด Verification

---

> **Engineer's Note:**
> "จำไว้ว่า AI รับผิดชอบ Outage แทนคุณไม่ได้ เพราะมันไม่มีเงินเดือนให้หัก ระบบนี้จึงไม่ได้ถูกออกแบบมาเพื่อให้มันฉลาดขึ้น แต่ถูกออกแบบมาเพื่อให้คุณ 'คนถือกุญแจ' ไม่ต้องตื่นมาพบว่า Repo กลายเป็นกองเถ้าถ่านในเช้าวันถัดไป"

**เอกสารฉบับนี้คือ Baseline มาตรฐาน เก็บไว้ที่ `docs/CSEA-SRS.md` และใช้กำกับดูแล Agent ของคุณอย่างเคร่งครัดครับ**
