#!/usr/bin/env python3
"""
Debug folder isolation with Apple-specific queries
"""
import sys
import os
from dotenv import load_dotenv

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from app.services.search_service import SearchService

def test_with_debug():
    """Test folder isolation with debug output"""

    print("=" * 60)
    print("Debug Folder Isolation Test")
    print("=" * 60)
    print()

    service = SearchService()

    # Test 1: Apple-specific query on folder_1
    print("Test 1: Search folder_1 for 'iPhone'")
    print("-" * 60)
    folder_1_results = service.search_with_folder_filter(
        query="iPhone",
        folder_id=1,
        top=3,
        use_semantic=True,
        debug=True
    )

    print(f"\n✅ Found {len(folder_1_results)} results in folder_1")
    for i, result in enumerate(folder_1_results, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print(f"     Preview: {result['content'][:100]}...")
        print()

    # Test 2: Generic "revenue" query on folder_1
    print("Test 2: Search folder_1 for 'revenue'")
    print("-" * 60)
    folder_1_revenue = service.search_with_folder_filter(
        query="revenue",
        folder_id=1,
        top=3,
        use_semantic=True,
        debug=True
    )

    print(f"\n✅ Found {len(folder_1_revenue)} results in folder_1")
    for i, result in enumerate(folder_1_revenue, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print(f"     Preview: {result['content'][:100]}...")
        print()

    # Test 3: Oracle-specific query on folder_2
    print("Test 3: Search folder_2 for 'Oracle'")
    print("-" * 60)
    folder_2_results = service.search_with_folder_filter(
        query="Oracle",
        folder_id=2,
        top=3,
        use_semantic=True,
        debug=True
    )

    print(f"\n✅ Found {len(folder_2_results)} results in folder_2")
    for i, result in enumerate(folder_2_results, 1):
        print(f"  {i}. {result['title']} (folder_id: {result['folder_id']})")
        print(f"     Score: {result['score']:.2f}")
        print(f"     Preview: {result['content'][:100]}...")
        print()

    # Test 4: Generic query with debug to see folder distribution
    print("Test 4: Search all for 'revenue' (see distribution)")
    print("-" * 60)
    all_results = service.search_with_folder_filter(
        query="revenue",
        folder_id=1,  # Requesting folder_1 but let's see what's in raw results
        top=3,
        use_semantic=True,
        debug=True
    )
    print()

    print("=" * 60)
    print("✅ Debug Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_with_debug()
