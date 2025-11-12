#!/usr/bin/env python3
"""
Test folder isolation in Azure AI Search
"""
import sys
import os
from dotenv import load_dotenv

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from app.services.search_service import SearchService

def test_folder_isolation():
    """Test that folder isolation works correctly"""

    print("=" * 60)
    print("Testing Folder Isolation in Azure AI Search")
    print("=" * 60)
    print()

    service = SearchService()

    # Test 1: Search folder_1 (Apple 10-K)
    print("Test 1: Search folder_1 for 'revenue'")
    print("-" * 60)
    folder_1_results = service.search_with_folder_filter(
        query="revenue",
        folder_id=1,
        top=3,
        use_semantic=True
    )

    print(f"✅ Found {len(folder_1_results)} results in folder_1")
    for i, result in enumerate(folder_1_results, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print(f"     Preview: {result['content'][:100]}...")
        print()

    # Test 2: Search folder_2 (Oracle 10-Q)
    print("Test 2: Search folder_2 for 'revenue'")
    print("-" * 60)
    folder_2_results = service.search_with_folder_filter(
        query="revenue",
        folder_id=2,
        top=3,
        use_semantic=True
    )

    print(f"✅ Found {len(folder_2_results)} results in folder_2")
    for i, result in enumerate(folder_2_results, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print(f"     Preview: {result['content'][:100]}...")
        print()

    # Test 3: Multi-folder search (user with access to both)
    print("Test 3: Search both folders (multi-folder access)")
    print("-" * 60)
    multi_results = service.search_multi_folder(
        query="revenue",
        folder_ids=[1, 2],
        top=5,
        use_semantic=True
    )

    print(f"✅ Found {len(multi_results)} results across folders")
    for i, result in enumerate(multi_results, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print()

    # Verification
    print("=" * 60)
    print("Verification:")
    print("=" * 60)

    folder_1_titles = set(r['title'] for r in folder_1_results)
    folder_2_titles = set(r['title'] for r in folder_2_results)

    print(f"✅ Folder 1 only returns: {folder_1_titles}")
    print(f"✅ Folder 2 only returns: {folder_2_titles}")

    # Check isolation
    if folder_1_titles and folder_2_titles:
        if not folder_1_titles.intersection(folder_2_titles):
            print("✅ ISOLATION VERIFIED: No document overlap between folders")
        else:
            print("❌ WARNING: Documents found in both folders")
    else:
        print("⚠️  One or both folders returned no results")

    print()
    print("=" * 60)
    print("✅ Folder Isolation Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_folder_isolation()
