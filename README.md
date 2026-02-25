# Dogbro Index

A Python-based trading application using the Shioaji API for Taiwan financial markets, featuring implied volatility calculations and options trading capabilities.

## Repository Architecture

```
dogbro-index/
├── main.py                 # Application entry point
├── pyproject.toml          # Project metadata and dependencies
├── .env.example            # Environment variables template
├── .gitignore              # Git ignore rules
│
└── src/
    ├── sj_trading/         # Trading logic and calculations
    │   ├── __init__.py
    │   └── xq_ivolatility.py    # XQ-style implied volatility calculator
    │
    └── utils/              # Utility modules
        ├── __init__.py
        └── config.py       # Configuration management with validation
```

## Features

- **Shioaji API Integration**: Connect to Taiwan stock/futures/options markets
- **Configuration Management**: Type-safe configuration with environment variable validation
- **Implied Volatility Calculator**: XQ-style Black-Scholes IV calculator
- **Clean Architecture**: SOLID principles with immutable config and proper separation of concerns

## Setup

### Prerequisites

- Python >= 3.12
- Shioaji API credentials (API key, secret key, CA certificate)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/julian7862/dogbro-index.git
cd dogbro-index
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e .
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

## Configuration

Required environment variables (see `.env.example`):

- `API_KEY`: Your Shioaji API key
- `SECRET_KEY`: Your Shioaji secret key
- `CA_CERT_PATH`: Path to your CA certificate (.pfx file)
- `CA_PASSWORD`: Password for the CA certificate

## Usage

Run the main application:

```bash
python main.py
```

### Using the IV Calculator

```python
from src.sj_trading.xq_ivolatility import XQIVolatility

# Calculate implied volatility
iv = XQIVolatility.ivolatility(
    call_put_flag="C",      # "C" for call, "P" for put
    spot_price=18000,       # Current spot price
    strike_price=18500,     # Strike price
    d_to_m=30,              # Days to maturity
    rate_100=2.0,           # Risk-free rate (%)
    b_100=2.0,              # Cost of carry (%)
    option_price=150        # Market option price
)
print(f"Implied Volatility: {iv}%")
```

## Architecture Principles

### Configuration (`src/utils/config.py`)
- **Immutable**: Using frozen dataclass to prevent accidental modification
- **Fail-fast**: Validates all required environment variables on startup
- **Type-safe**: Full type hints for better IDE support and error detection
- **Single source of truth**: Global config instance loaded once

### Trading Modules (`src/sj_trading/`)
- **Black-Scholes Model**: Standard options pricing implementation
- **XQ-style IV**: Binary search algorithm for implied volatility calculation
- **Clean interfaces**: Clear method signatures and documentation

## Development

### Project Structure Rationale

- `main.py`: Entry point keeps the root clean and obvious
- `src/`: Source code separated from configuration and documentation
- `src/utils/`: Shared utilities (config, helpers) isolated from business logic
- `src/sj_trading/`: Domain-specific trading logic and calculations

### Code Style

- Follow PEP 8 guidelines
- Use type hints for function signatures
- Implement dataclasses for data structures
- Document complex algorithms and business logic

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
