# 🛍️ MAVEN - AI Shopping Assistant

**M**ulti-**A**gent **V**alue and **E**xploratory **N**etwork

An intelligent shopping assistant powered by LangGraph and multiple AI agents that researches products, compares prices, finds images, and provides personalized recommendations.

![Maven Architecture](https://img.shields.io/badge/LangGraph-Multi--Agent-blue)
![Python](https://img.shields.io/badge/Python-3.13-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.122-teal)

## ✨ Features

- 🤖 **Multi-Agent System** - Coordinated AI agents working together using LangGraph
- 🔍 **Deep Product Research** - Searches the web using Tavily API for comprehensive product data
- 💰 **Price Comparison** - Finds best prices across multiple retailers (domain-agnostic)
- 🖼️ **Images (optional)** - Image lookup is currently disabled in the pipeline
- ⭐ **Verified Ratings** - Extracts and validates product ratings (1.0-5.0)
- 📊 **Detailed Analysis** - Provides pros, cons, features, and buying recommendations
- 🎨 **Beautiful UI** - Modern, responsive interface with real-time updates

## 🏗️ Architecture

Maven uses a **LangGraph-based multi-agent workflow**:

```
┌─────────────┐
│   Manager   │ ─── Analyzes user query and coordinates agents
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│ Primary Researcher  │ ─── Searches web for top product candidates
└──────────┬──────────┘
           │
           ▼
┌──────────────────────┐
│ Product Specialist   │ ─── Deep analysis of specs, reviews, ratings
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Price Comparison     │ ─── Compares prices across retailers
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Scraper/Formatter    │ ─── Compiles final recommendations
└──────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- Gemini API Key (if using `LLM_PROVIDER=gemini`)
- Tavily API Key (for web search)
- Groq API Key (if using `LLM_PROVIDER=groq`)

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd anti_maven
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Copy the sample env and edit values:
   ```bash
   cp .env.example .env
   ```

   Required `.env` fields:
   ```env
   LLM_PROVIDER=gemini
   TAVILY_API_KEY=your_tavily_api_key_here
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   GROQ_API_KEY=your_groq_api_key_here
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

   Get your API keys:
   - **Google Gemini**: https://ai.google.dev/
   - **Tavily**: https://tavily.com/
   - **Groq**: https://groq.com/

5. **Run the application**
   ```bash
   python main.py
   ```

6. **Open in browser**
   
   Navigate to: `http://localhost:8000`

## 📁 Project Structure

```
anti_maven/
├── agents.py           # AI agent implementations
├── agent_graph.py      # LangGraph workflow definition
├── models.py           # Pydantic data models
├── main.py            # FastAPI server
├── index.html         # Frontend UI
├── requirements.txt   # Python dependencies
├── .env              # Environment variables (create this)
└── README.md         # This file
```

## 🎯 Usage

### Web Interface

1. Open `http://localhost:8000` in your browser
2. Enter a product query (e.g., "best wireless headphones under $200")
3. Wait for Maven to research and analyze products
4. Review the recommendations, prices, and images
5. Click on product links to purchase

### Example Queries

- "best noise cancelling headphones"
- "gaming laptop under $1000"
- "budget mechanical keyboard"
- "4K monitor for photo editing"
- "wireless earbuds for running"

### API Endpoint

**POST** `/api/research`

```json
{
  "query": "best wireless headphones"
}
```

**Response:**
```json
{
  "products": [
    {
      "name": "Sony WH-1000XM5",
      "price": "$299.99",
      "rating": 4.7,
      "image_url": "https://...",
      "pros": ["Excellent ANC", "Superior sound quality"],
      "cons": ["Expensive"],
      "price_comparison": [
        {
          "retailer": "Amazon",
          "price": 299.99,
          "url": "https://..."
        }
      ],
      "cheapest_link": "https://..."
    }
  ],
  "final_recommendation": "**Sony WH-1000XM5** offers the best..."
}
```

## 🤖 Agents

### 1. Manager Agent
- Analyzes user intent
- Coordinates other agents
- Determines search strategy

### 2. Primary Researcher Agent
- Searches web using Tavily API
- Identifies top 5 product candidates
- Extracts initial product URLs

### 3. Product Specialist Agent
- Deep-dives into each product
- Analyzes specs, features, reviews
- Extracts pros/cons and ratings
- **Ensures every product has 1.0-5.0 rating**

### 4. Image Search Agent
Removed (image lookup is currently disabled in the pipeline).

### 5. Price Comparison Agent
- Searches multiple retailers
- Extracts pricing information
- Finds cheapest buying option
- Provides direct purchase links

### 6. Scraper/Formatter Agent
- Compiles all agent outputs
- Generates final recommendations
- Formats results for display

## 🔧 Configuration

### LLM Models

Set provider and model through `.env` only:

```env
LLM_PROVIDER=gemini  # gemini or groq
GEMINI_MODEL=gemini-2.5-flash
GROQ_MODEL=llama-3.3-70b-versatile
```

### Search Tools

- **Tavily**: Primary web search for product research
- **DuckDuckGo**: Image search for product photos

## 🎨 Frontend Features

- **Modern Design**: Clean, minimalist UI with Tailwind CSS
- **Real-time Loading**: Shows agent progress during research
- **Star Ratings**: Visual 5-star rating system
- **Price Cards**: Comparison table showing retailer prices
- **Markdown Support**: Rich text recommendations
- **Responsive**: Works on desktop, tablet, and mobile

## 📊 Data Models

### Product
```python
class Product(BaseModel):
    name: str
    price: Union[str, float, int]
    rating: float  # Always 1.0-5.0
    reviews_count: Optional[int]
    features: List[str]
    pros: List[str]
    cons: List[str]
    url: str
    image_url: str  # Single best image
    why_to_buy: Optional[str]
    price_comparison: List[RetailerPrice]
    cheapest_link: Optional[str]
```

### RetailerPrice
```python
class RetailerPrice(BaseModel):
    retailer: str
    price: Union[str, float, int]
    url: str
    availability: str
```

## 🧪 Testing

Run the test script:
```bash
python test_simple.py
```

This will:
- Test the complete agent workflow
- Verify image URLs are valid
- Check ratings are numeric (1.0-5.0)
- Save results to `test_results_updated.json`

## 🔐 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `LLM_PROVIDER` | Active LLM provider (`gemini` or `groq`) | Yes |
| `TAVILY_API_KEY` | Tavily search API key | Yes |
| `GEMINI_API_KEY` | Gemini API key | Yes (if `LLM_PROVIDER=gemini`) |
| `GEMINI_MODEL` | Gemini model id | Yes (if `LLM_PROVIDER=gemini`) |
| `GROQ_API_KEY` | Groq API key | Yes (if `LLM_PROVIDER=groq`) |
| `GROQ_MODEL` | Groq model id | Yes (if `LLM_PROVIDER=groq`) |

## 🚦 Rate Limits

Be aware of API rate limits:
- **Gemini**: 60 requests/minute (free tier)
- **Tavily**: 1000 requests/month (free tier)
- **DuckDuckGo**: No official limit, use responsibly

## 🐛 Troubleshooting

### Port 8000 already in use
```bash
lsof -ti:8000 | xargs kill -9
python main.py
```

### Missing API keys
```
ValueError: GEMINI_API_KEY is required when LLM_PROVIDER=gemini
```
→ Create `.env` file with your API keys

### Slow performance
- Reduce `max_results` in `agents.py`
- Use faster LLM model (e.g., `gemini-flash`)
- Optimize search queries

### No images found
- Check DuckDuckGo is not blocked
- Verify `ddgs` package is installed
- Check internet connection

## 📝 License

MIT License - Feel free to use and modify

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Add more retailers for price comparison
- Implement caching for faster responses
- Add user reviews sentiment analysis
- Support multiple languages
- Add product comparison feature
- Implement price drop alerts

## 🙏 Acknowledgments

Built with:
- [LangChain](https://langchain.com/) - LLM framework
- [LangGraph](https://langchain-ai.github.io/langgraph/) - Multi-agent orchestration
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Google Gemini](https://ai.google.dev/) - LLM
- [Tavily](https://tavily.com/) - Search API
- [Tailwind CSS](https://tailwindcss.com/) - Styling

## 📧 Support

For issues and questions, please open a GitHub issue.

---

**Made with ❤️ using LangGraph Multi-Agent Architecture**
