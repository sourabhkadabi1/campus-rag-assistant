#!/usr/bin/env python3
"""
Seed sample profiles and course material for local testing.

Seeds:
1. Test Student (free plan) — UUID: 00000000-0000-0000-0000-000000000001 (Sem 3, CSE)
2. Test Paid Student (paid plan) — UUID: 00000000-0000-0000-0000-000000000002 (Sem 3, CSE)
3. Test Admin — UUID: 00000000-0000-0000-0000-000000000000
4. Sample DBMS Document & Chunks on Normalization (Chapter 2, Pages 45-60)
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services.embeddings import get_embeddings_batch
import asyncpg


CHUNKS_DATA = [
    {
        "chapter_no": 2,
        "chapter_title": "Relational Database Design and Normalization",
        "page_start": 45,
        "page_end": 48,
        "content": (
            "Normalization is the process of organizing data in a relational database to reduce data redundancy "
            "and improve data integrity. It involves decomposing larger, potentially problematic tables into smaller, "
            "well-structured tables without losing information. The primary goals are to eliminate insertion, deletion, "
            "and update anomalies.\n\n"
            "Functional Dependency: Given a relation R, a set of attributes X functionally determines Y (denoted X -> Y) "
            "if whenever two tuples have the same value for X, they must have the same value for Y. "
            "A key requirement for normalization is understanding candidate keys and prime vs non-prime attributes."
        ),
    },
    {
        "chapter_no": 2,
        "chapter_title": "Relational Database Design and Normalization",
        "page_start": 49,
        "page_end": 52,
        "content": (
            "First Normal Form (1NF): A relation is in 1NF if and only if every attribute contains only atomic (indivisible) "
            "values, and each column contains values of a single type. Multi-valued attributes and composite attributes are disallowed.\n\n"
            "Second Normal Form (2NF): A relation is in 2NF if it is in 1NF and no non-prime attribute is partially dependent "
            "on any candidate key of the relation. In other words, every non-prime attribute must be fully functionally dependent "
            "on the entire primary key. If the primary key is a single attribute, the relation is automatically in 2NF if it is in 1NF."
        ),
    },
    {
        "chapter_no": 2,
        "chapter_title": "Relational Database Design and Normalization",
        "page_start": 53,
        "page_end": 56,
        "content": (
            "Third Normal Form (3NF): A relation is in 3NF if it is in 2NF and no non-prime attribute is transitively dependent "
            "on any candidate key. Formally, for every non-trivial functional dependency X -> A:\n"
            "1. X is a superkey, OR\n"
            "2. A is a prime attribute (part of some candidate key).\n\n"
            "Boyce-Codd Normal Form (BCNF): A stronger version of 3NF. A relation is in BCNF if for every non-trivial "
            "functional dependency X -> A, X is a superkey. BCNF strictly eliminates all redundancies that can be predicted "
            "using functional dependencies alone."
        ),
    },
    {
        "chapter_no": 2,
        "chapter_title": "Relational Database Design and Normalization",
        "page_start": 57,
        "page_end": 60,
        "content": (
            "Comparison of 3NF vs BCNF:\n"
            "- Lossless Join: Both 3NF and BCNF decompositions can always achieve the lossless-join property.\n"
            "- Dependency Preservation: 3NF decompositions are always guaranteed to preserve all functional dependencies. "
            "However, BCNF decompositions may not always preserve all functional dependencies.\n"
            "- Redundancy: BCNF has strictly less redundancy than 3NF because it removes condition 2 of 3NF (which allows non-superkey determinants if the right side is prime).\n\n"
            "Example: Consider R(Student, Course, Instructor) with dependencies (Student, Course) -> Instructor and Instructor -> Course. "
            "This relation is in 3NF (Course is prime) but not in BCNF (Instructor is not a superkey)."
        ),
    },
]


async def seed():
    print(f"Connecting to {settings.database_url[:35]}...")
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)
    try:
        # 1. Fetch Plan IDs
        free_plan_id = await conn.fetchval("SELECT id FROM plans WHERE name = 'free'")
        paid_plan_id = await conn.fetchval("SELECT id FROM plans WHERE name = 'paid'")

        print(f"Plans found: Free={free_plan_id}, Paid={paid_plan_id}")

        # 2. Seed Profiles
        test_student_id = "00000000-0000-0000-0000-000000000001"
        test_paid_id = "00000000-0000-0000-0000-000000000002"
        test_admin_id = "00000000-0000-0000-0000-000000000000"

        await conn.execute(
            """INSERT INTO profiles (id, email, full_name, role, department, semester, roll_no, plan_id, is_verified)
               VALUES 
               ($1, 'student@pesu.edu', 'Test Student', 'student', 'CSE', 3, 'PES1202300001', $4, TRUE),
               ($2, 'paid_student@pesu.edu', 'Test Paid Student', 'student', 'CSE', 3, 'PES1202300002', $5, TRUE),
               ($3, 'admin@pesu.edu', 'Test Admin', 'admin', 'CSE', 3, 'PESADMIN0001', $5, TRUE)
               ON CONFLICT (id) DO UPDATE
               SET plan_id = EXCLUDED.plan_id, role = EXCLUDED.role, department = EXCLUDED.department, semester = EXCLUDED.semester""",
            test_student_id, test_paid_id, test_admin_id, free_plan_id, paid_plan_id
        )
        print("✓ Test profiles seeded (Free student, Paid student, Admin)")

        # 3. Seed Document
        doc_id = "11111111-1111-1111-1111-111111111111"
        await conn.execute(
            """INSERT INTO documents (
                   id, filename, original_filename, department, semester, subject,
                   academic_year, doc_type, is_active, file_path, file_size_bytes,
                   total_pages, ingestion_status, uploaded_by
               ) VALUES (
                   $1, 'dbms_silberschatz_sample.pdf', 'Database System Concepts (Silberschatz).pdf',
                   'CSE', 3, 'DBMS', '2026-27', 'book', TRUE, 'uploads/sample.pdf',
                   102400, 60, 'done', $2
               ) ON CONFLICT (id) DO UPDATE SET is_active = TRUE, ingestion_status = 'done'""",
            doc_id, test_admin_id
        )
        print("✓ Sample DBMS document seeded")

        # 4. Generate Embeddings & Seed Chunks
        contents = [c["content"] for c in CHUNKS_DATA]
        print(f"Generating local embeddings for {len(contents)} chunks...")
        embeddings = get_embeddings_batch(contents)

        # Clear existing chunks for this document
        await conn.execute("DELETE FROM chunks WHERE document_id = $1", doc_id)

        for i, (chunk, emb) in enumerate(zip(CHUNKS_DATA, embeddings)):
            emb_str = "[" + ",".join(str(x) for x in emb) + "]"
            chunk_id = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO chunks (
                       id, document_id, content, embedding, semester, department,
                       subject, academic_year, doc_type, chapter_no, chapter_title,
                       page_start, page_end, chunk_index, token_count
                   ) VALUES (
                       $1, $2, $3, $4::vector, 3, 'CSE', 'DBMS', '2026-27', 'book',
                       $5, $6, $7, $8, $9, $10
                   )""",
                chunk_id, doc_id, chunk["content"], emb_str,
                chunk["chapter_no"], chunk["chapter_title"],
                chunk["page_start"], chunk["page_end"], i, len(chunk["content"].split())
            )
        print(f"✓ {len(CHUNKS_DATA)} chunks inserted with pgvector embeddings")

    finally:
        await conn.close()
    print("\nAll sample data seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
