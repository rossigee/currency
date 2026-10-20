# Lightning Network Module - Development Makefile
# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

.PHONY: help lint fix clean test install dev-setup check-deps

# Default target
help:
	@echo "Lightning Network Module - Development Commands"
	@echo "=============================================="
	@echo ""
	@echo "Quality Assurance:"
	@echo "  lint          Run comprehensive code quality checks"
	@echo "  fix           Auto-fix common formatting issues"
	@echo "  clean         Remove temporary and cache files"
	@echo ""
	@echo "Development:"
	@echo "  test          Run unit tests (if available)"
	@echo "  check-deps    Check external dependencies"
	@echo "  dev-setup     Set up development environment"
	@echo ""
	@echo "Examples:"
	@echo "  make lint     # Check code quality"
	@echo "  make fix      # Auto-fix whitespace and formatting"
	@echo "  make clean    # Clean up temp files"

# Run comprehensive linting
lint:
	@echo "🔍 Running code quality checks..."
	@./lint.sh

# Auto-fix common issues
fix:
	@echo "🔧 Auto-fixing common formatting issues..."
	@echo "Removing trailing whitespace..."
	@find . -name "*.py" -type f -exec sed -i 's/[[:space:]]*$$//' {} \;
	@find . -name "*.xml" -type f -exec sed -i 's/[[:space:]]*$$//' {} \;
	@find . -name "*.js" -type f -exec sed -i 's/[[:space:]]*$$//' {} \;
	@echo "Converting tabs to spaces (4-space indentation)..."
	@find . -name "*.py" -type f -exec sed -i 's/\t/    /g' {} \;
	@echo "✅ Auto-fix complete. Run 'make lint' to verify."

# Clean temporary files
clean:
	@echo "🧹 Cleaning temporary and cache files..."
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyo" -delete
	@find . -name ".DS_Store" -delete 2>/dev/null || true
	@find . -name "Thumbs.db" -delete 2>/dev/null || true
	@find . -name "*.tmp" -delete
	@find . -name "*.bak" -delete
	@echo "✅ Cleanup complete."

# Run tests
test:
	@echo "🧪 Running unit tests..."
	@if [ -d "tests" ]; then \
		python3 -m pytest tests/ -v; \
	else \
		echo "No tests directory found. Create tests/ with your unit tests."; \
	fi

# Check external dependencies
check-deps:
	@echo "📦 Checking external dependencies..."
	@echo "Python dependencies:"
	@python3 -c "import requests; print('  ✅ requests')" 2>/dev/null || echo "  ❌ requests (missing)"
	@python3 -c "import qrcode; print('  ✅ qrcode')" 2>/dev/null || echo "  ❌ qrcode (missing)"
	@python3 -c "import dateutil; print('  ✅ python-dateutil')" 2>/dev/null || echo "  ❌ python-dateutil (missing)"
	@echo "System tools:"
	@which xmllint >/dev/null && echo "  ✅ xmllint" || echo "  ❌ xmllint (install libxml2-utils)"
	@which python3 >/dev/null && echo "  ✅ python3" || echo "  ❌ python3 (missing)"

# Development environment setup
dev-setup:
	@echo "🔧 Setting up development environment..."
	@echo "Installing Python dependencies..."
	@pip3 install --user requests qrcode python-dateutil pytest flake8 2>/dev/null || echo "Install pip3 and try again"
	@echo "Making scripts executable..."
	@chmod +x lint.sh
	@echo "✅ Development setup complete."
	@echo "Next steps:"
	@echo "  1. Run 'make check-deps' to verify all dependencies"
	@echo "  2. Run 'make lint' to check code quality"
	@echo "  3. Run 'make test' to run unit tests"

# Pre-release checklist
release-check: clean lint
	@echo "🚀 Pre-release checklist..."
	@echo "Checking module structure..."
	@test -f __manifest__.py || (echo "❌ Missing __manifest__.py" && exit 1)
	@test -f __init__.py || (echo "❌ Missing __init__.py" && exit 1)
	@test -d models || (echo "❌ Missing models directory" && exit 1)
	@test -d views || (echo "❌ Missing views directory" && exit 1)
	@test -d security || (echo "❌ Missing security directory" && exit 1)
	@echo "✅ Module structure looks good."
	@echo "🎉 Ready for release!"

# Quick development cycle
dev: fix lint
	@echo "🔄 Development cycle complete."