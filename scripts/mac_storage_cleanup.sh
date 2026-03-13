#!/bin/bash
# Safe macOS storage cleanup. Run from project root or anywhere.
# Frees: pip cache, npm cache, Xcode DerivedData, Homebrew, Colima, unavailable simulators.
set -e
FREED=0
echo "=== Safe storage cleanup ==="

if command -v pip3 &>/dev/null; then
  echo "Purging pip cache..."
  pip3 cache purge 2>/dev/null && echo "  pip: done" || true
fi

echo "Clearing Xcode DerivedData..."
rm -rf ~/Library/Developer/Xcode/DerivedData/* 2>/dev/null && echo "  DerivedData: cleared" || true

echo "Cleaning Homebrew..."
brew cleanup --prune=all -s 2>/dev/null && echo "  Homebrew: done" || true

echo "Removing unavailable iOS simulators..."
xcrun simctl delete unavailable 2>/dev/null && echo "  Simulators: done" || true

echo "Clearing Colima cache..."
rm -rf ~/Library/Caches/colima/* 2>/dev/null && echo "  Colima: done" || true

echo ""
echo "Optional (manual):"
echo "  - Empty Trash: Finder -> Empty Trash"
echo "  - iOS Simulators (reclaim ~6GB if you don't need them): xcrun simctl delete all"
echo "  - Storage Settings: Apple menu -> About This Mac -> Storage -> Manage"
echo "Done."
