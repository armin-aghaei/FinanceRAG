#!/usr/bin/env python3
"""
Final comprehensive folder isolation test
Tests with document-specific queries to verify isolation
"""
import sys
import os
from dotenv import load_dotenv

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from app.services.search_service import SearchService

def test_folder_isolation():
    """Comprehensive test that folder isolation works correctly"""

    print("=" * 60)
    print("Folder Isolation Verification Test")
    print("=" * 60)
    print()

    service = SearchService()

    # Test 1: Apple-specific query on folder_1
    print("Test 1: Search folder_1 for 'iPhone' (Apple 10-K)")
    print("-" * 60)
    folder_1_iphone = service.search_with_folder_filter(
        query="iPhone",
        folder_id=1,
        top=3,
        use_semantic=True
    )

    print(f"✅ Found {len(folder_1_iphone)} results in folder_1")
    for i, result in enumerate(folder_1_iphone, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print(f"     Preview: {result['content'][:80]}...")
        print()

    # Test 2: Apple-specific query on folder_2 (should be empty)
    print("Test 2: Search folder_2 for 'iPhone' (should be empty)")
    print("-" * 60)
    folder_2_iphone = service.search_with_folder_filter(
        query="iPhone",
        folder_id=2,
        top=3,
        use_semantic=True
    )

    if len(folder_2_iphone) == 0:
        print("✅ Correctly returned 0 results (iPhone not in Oracle docs)")
    else:
        print(f"❌ WARNING: Found {len(folder_2_iphone)} results (should be 0)")
    print()

    # Test 3: Oracle-specific query on folder_2
    print("Test 3: Search folder_2 for 'Oracle database' (Oracle 10-Q)")
    print("-" * 60)
    folder_2_oracle = service.search_with_folder_filter(
        query="Oracle database",
        folder_id=2,
        top=3,
        use_semantic=True
    )

    print(f"✅ Found {len(folder_2_oracle)} results in folder_2")
    for i, result in enumerate(folder_2_oracle, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print(f"     Preview: {result['content'][:80]}...")
        print()

    # Test 4: Oracle-specific query on folder_1 (should be empty)
    print("Test 4: Search folder_1 for 'Oracle database' (should be empty)")
    print("-" * 60)
    folder_1_oracle = service.search_with_folder_filter(
        query="Oracle database",
        folder_id=1,
        top=3,
        use_semantic=True
    )

    if len(folder_1_oracle) == 0:
        print("✅ Correctly returned 0 results (Oracle not in Apple docs)")
    else:
        print(f"❌ WARNING: Found {len(folder_1_oracle)} results (should be 0)")
    print()

    # Test 5: Multi-folder search
    print("Test 5: Search both folders for 'financial statements'")
    print("-" * 60)
    multi_results = service.search_multi_folder(
        query="financial statements",
        folder_ids=[1, 2],
        top=6,
        use_semantic=True
    )

    print(f"✅ Found {len(multi_results)} results across both folders")
    folder_1_count = sum(1 for r in multi_results if r['folder_id'] == 1)
    folder_2_count = sum(1 for r in multi_results if r['folder_id'] == 2)
    print(f"   - Folder 1 (Apple): {folder_1_count} results")
    print(f"   - Folder 2 (Oracle): {folder_2_count} results")
    print()

    for i, result in enumerate(multi_results, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print()

    # Verification Summary
    print("=" * 60)
    print("Isolation Verification Summary:")
    print("=" * 60)

    isolation_tests = [
        ("Apple content in folder_1", len(folder_1_iphone) > 0),
        ("Apple content NOT in folder_2", len(folder_2_iphone) == 0),
        ("Oracle content in folder_2", len(folder_2_oracle) > 0),
        ("Oracle content NOT in folder_1", len(folder_1_oracle) == 0),
        ("Multi-folder returns both", folder_1_count > 0 and folder_2_count > 0)
    ]

    all_passed = True
    for test_name, passed in isolation_tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("🎉 ALL ISOLATION TESTS PASSED!")
        print("Folder isolation is working correctly.")
    else:
        print("⚠️  Some isolation tests failed - review results above")

    print("=" * 60)

if __name__ == "__main__":
    test_folder_isolation()
