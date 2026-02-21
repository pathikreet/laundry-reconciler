# Implementation Plan

This document outlines the implementation plan for the Laundry Reconciler MVP.

## Milestone 1: Foundation (Completed)

- [x] **Initialize Project Structure**: Created `src/` directory with submodules.
- [x] **Implement Database Schema (DATA-001)**: Implemented SQLAlchemy models for `Order`, `PaymentEvent`, `DeliveryEvent`, `ReconciliationRun`, `AuditLog`, `CashRegisterEntry`, `ColumnMapping`, `ToleranceConfig`.
- [x] **Implement Data Access Layer (DATA-002)**: Implemented repositories for all models.
- [x] **Implement Configuration Management (CFG-001)**: Implemented `Settings` class using Pydantic.
- [x] **Unit Tests (TEST-001)**: Implemented and passed tests for database and repositories.

## Milestone 2: Import Pipeline

- [ ] **CRM Import (IMP-001)**: Implement parser for CRM Excel/CSV files.
- [ ] **MSWIPE Import (IMP-002)**: Implement parser for MSWIPE CSV files.
- [ ] **Cash Register Import (IMP-003)**: Implement parser for Cash Register Excel grid.
- [ ] **Notepad Import (IMP-004)**: Implement manual entry system.
- [ ] **Column Mapping (IMP-005)**: Implement reusable column mapping engine.

## Milestone 3: Matching Engine

- [ ] **Exact Match (MATCH-001)**: Implement exact order matching.
- [ ] **Fuzzy Match (MATCH-002)**: Implement fuzzy matching.
- [ ] **Confidence Scoring (MATCH-003)**: Implement confidence scoring.

## Milestone 4: Reconciliation Rules

- [ ] **Order Ledger (RECON-001)**: Implement order mini-ledger.
- [ ] **Delivery Rules (RECON-002)**: Implement delivery status rules.
- [ ] **Payment Rules (RECON-003)**: Implement payment rules.
- [ ] **Credit Policy (RECON-004)**: Implement credit policy enforcement.
- [ ] **GPay Validation (RECON-005)**: Implement GPay validation.
- [ ] **Cash Validation (RECON-006)**: Implement cash validation.

## Milestone 5: User Interface

- [ ] **Import Wizard (UI-001)**: Implement import wizard screens.
- [ ] **Results Table (UI-002)**: Implement results table.
- [ ] **Exceptions Queue (UI-003)**: Implement exceptions queue.
- [ ] **Daily Summary (UI-004)**: Implement daily summary dashboard.

## Milestone 6: Export & Polish

- [ ] **Excel Export (EXP-001)**: Implement Excel export.
- [ ] **Error Handling (NFR-001)**: Implement error handling.
- [ ] **Logging (NFR-002)**: Implement audit logging.
- [ ] **OCR Feature (OPT-001)**: Implement OCR for notepad screenshots.

## Milestone 7: Testing

- [ ] **Unit Tests**: Implement unit tests for all components.
- [ ] **Integration Tests**: Implement end-to-end integration tests.
