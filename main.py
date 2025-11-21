"""
Streamlit Plagiarism Checker Application
Run with: streamlit run app.py
"""

# ---------- Install dependencies (if needed) ----------
# pip install streamlit python-docx PyPDF2 requests beautifulsoup4 plotly

import streamlit as st
import io
import re
import time
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import plotly.graph_objects as go
import plotly.express as px

# Try importing optional modules
try:
    from PyPDF2 import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# ---------- CONFIG ----------
MIN_WORDS_PER_PHRASE = 6
MAX_PHRASES_TO_CHECK = 15
SEARCH_DELAY = 2

# ---------- PAGE CONFIG ----------
st.set_page_config(
    page_title="Plagiarism Checker",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- CUSTOM CSS ----------
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        color: #1f77b4;
        padding: 1rem 0;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .source-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin: 0.5rem 0;
    }
    .phrase-card {
        background: #fff3cd;
        padding: 0.8rem;
        border-radius: 6px;
        border-left: 3px solid #ffc107;
        margin: 0.5rem 0;
    }
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
</style>
""", unsafe_allow_html=True)

# ---------- SESSION STATE ----------
if 'results' not in st.session_state:
    st.session_state.results = None
if 'analyzing' not in st.session_state:
    st.session_state.analyzing = False

# ---------- FILE LOADING ----------
def load_file(uploaded_file):
    """Load text from uploaded file."""
    try:
        ext = uploaded_file.name.split('.')[-1].lower()
        content = uploaded_file.read()
        
        if ext == 'txt':
            return content.decode('utf-8', errors='ignore')
        
        elif ext == 'pdf' and HAS_PDF:
            pdf = PdfReader(io.BytesIO(content))
            text = []
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text.append(extracted)
            return '\n'.join(text)
        
        elif ext in ['docx', 'doc'] and HAS_DOCX:
            doc = Document(io.BytesIO(content))
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        
        else:
            return content.decode('utf-8', errors='ignore')
            
    except Exception as e:
        st.error(f"Error loading file: {str(e)}")
        return ""

# ---------- TEXT PROCESSING ----------
def clean_text(text):
    """Clean and normalize text."""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_sentences(text):
    """Extract meaningful sentences from text."""
    text = clean_text(text)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    valid = []
    for s in sentences:
        s = s.strip()
        words = s.split()
        if len(words) >= MIN_WORDS_PER_PHRASE:
            if len(words) > 12:
                s = ' '.join(words[:12])
            valid.append(s)
    
    return valid

def get_search_phrases(text, max_phrases=MAX_PHRASES_TO_CHECK):
    """Get phrases to search for plagiarism."""
    sentences = extract_sentences(text)
    
    if not sentences:
        paragraphs = text.split('\n')
        for p in paragraphs:
            words = p.split()
            if len(words) >= MIN_WORDS_PER_PHRASE:
                phrase = ' '.join(words[:12])
                sentences.append(phrase)
    
    # Return unique phrases
    seen = set()
    unique = []
    for s in sentences:
        normalized = s.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(s)
    
    return unique[:max_phrases]

# ---------- SEARCH FUNCTIONS ----------
def search_duckduckgo(query):
    """Search DuckDuckGo for exact phrase."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    search_url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
    
    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        results = []
        for row in soup.find_all('tr')[1:6]:
            cells = row.find_all('td')
            if len(cells) >= 2:
                links = cells[0].find_all('a')
                if links:
                    link = links[0]
                    url = link.get('href', '')
                    title = link.get_text(strip=True)
                    snippet = cells[-1].get_text(strip=True)
                    
                    if url.startswith('http'):
                        query_words = set(query.lower().split())
                        snippet_words = set(snippet.lower().split())
                        overlap = len(query_words & snippet_words) / max(len(query_words), 1)
                        
                        if overlap > 0.3:
                            results.append({
                                'title': title,
                                'url': url,
                                'snippet': snippet,
                                'relevance': round(overlap * 100, 1)
                            })
        
        return results
    except:
        return []

def search_bing(query):
    """Search Bing as backup."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    search_url = f"https://www.bing.com/search?q={quote_plus(query)}"
    
    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        results = []
        for item in soup.find_all('li', class_='b_algo')[:5]:
            title_tag = item.find('h2')
            link_tag = item.find('a')
            snippet_tag = item.find('p')
            
            if title_tag and link_tag:
                url = link_tag.get('href', '')
                if url.startswith('http'):
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ''
                    query_words = set(query.lower().split())
                    snippet_words = set(snippet.lower().split())
                    overlap = len(query_words & snippet_words) / max(len(query_words), 1)
                    
                    if overlap > 0.3:
                        results.append({
                            'title': title_tag.get_text(strip=True),
                            'url': url,
                            'snippet': snippet,
                            'relevance': round(overlap * 100, 1)
                        })
        
        return results
    except:
        return []

def search_phrase(phrase):
    """Search for a phrase using multiple engines."""
    results = search_duckduckgo(phrase)
    if not results:
        results = search_bing(phrase)
    return results

# ---------- PLAGIARISM CHECK ----------
def check_plagiarism(text, max_phrases=MAX_PHRASES_TO_CHECK, progress_bar=None, status_text=None):
    """Check text for plagiarism against the internet."""
    
    # Extract phrases
    if status_text:
        status_text.text("📄 Extracting key phrases from document...")
    
    phrases = get_search_phrases(text, max_phrases)
    
    if not phrases:
        return None
    
    # Check each phrase
    results = []
    found_count = 0
    all_sources = {}
    
    for i, phrase in enumerate(phrases):
        if status_text:
            status_text.text(f"🔍 Checking phrase {i+1}/{len(phrases)}: \"{phrase[:50]}...\"")
        
        if progress_bar:
            progress_bar.progress((i + 1) / len(phrases))
        
        matches = search_phrase(phrase)
        is_found = len(matches) > 0
        
        if is_found:
            found_count += 1
            for m in matches[:2]:
                url = m['url']
                if url and url not in all_sources:
                    all_sources[url] = {
                        'url': url,
                        'title': m['title'],
                        'phrases_matched': [],
                        'relevance': m['relevance']
                    }
                if url:
                    all_sources[url]['phrases_matched'].append(phrase[:60])
        
        results.append({
            'phrase': phrase,
            'found': is_found,
            'sources': matches[:3]
        })
        
        time.sleep(SEARCH_DELAY)
    
    # Calculate statistics
    total = len(phrases)
    plagiarism_pct = round((found_count / total) * 100, 1) if total > 0 else 0
    
    # Determine severity
    if plagiarism_pct >= 60:
        severity = "CRITICAL"
        color = "#dc3545"
    elif plagiarism_pct >= 40:
        severity = "HIGH"
        color = "#fd7e14"
    elif plagiarism_pct >= 20:
        severity = "MEDIUM"
        color = "#ffc107"
    elif plagiarism_pct >= 10:
        severity = "LOW"
        color = "#28a745"
    else:
        severity = "MINIMAL"
        color = "#17a2b8"
    
    return {
        'plagiarism_percentage': plagiarism_pct,
        'severity': severity,
        'color': color,
        'total_checked': total,
        'found_online': found_count,
        'original': total - found_count,
        'sources': list(all_sources.values()),
        'detailed_results': results,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# ---------- VISUALIZATION ----------
def create_gauge_chart(percentage):
    """Create gauge chart for plagiarism percentage."""
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = percentage,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Plagiarism Score", 'font': {'size': 24}},
        delta = {'reference': 30},
        gauge = {
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "darkblue"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 10], 'color': '#d4edda'},
                {'range': [10, 20], 'color': '#c3e6cb'},
                {'range': [20, 40], 'color': '#fff3cd'},
                {'range': [40, 60], 'color': '#f8d7da'},
                {'range': [60, 100], 'color': '#f5c6cb'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': percentage
            }
        }
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'color': "darkblue", 'family': "Arial"}
    )
    
    return fig

def create_pie_chart(found, original):
    """Create pie chart for phrase distribution."""
    fig = go.Figure(data=[go.Pie(
        labels=['Found Online', 'Original'],
        values=[found, original],
        hole=.3,
        marker=dict(colors=['#fd7e14', '#28a745'])
    )])
    
    fig.update_layout(
        title="Phrase Analysis",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True
    )
    
    return fig

# ---------- MAIN APP ----------
def main():
    # Header
    st.markdown('<h1 class="main-header">🔍 Internet Plagiarism Checker</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/000000/find-matching-job.png", width=80)
        st.title("Settings")
        
        max_phrases = st.slider(
            "Number of phrases to check",
            min_value=5,
            max_value=20,
            value=15,
            help="More phrases = more accurate but slower"
        )
        
        st.markdown("---")
        st.subheader("📊 About")
        st.info("""
        This tool checks your document against the internet to detect potential plagiarism.
        
        **Features:**
        - Multi-engine search
        - Real-time analysis
        - Detailed reports
        - Source attribution
        """)
        
        st.markdown("---")
        st.subheader("📝 Supported Formats")
        st.write("✅ TXT")
        st.write("✅ PDF")
        st.write("✅ DOCX")
    
    # Main content
    tab1, tab2, tab3 = st.tabs(["📤 Upload Document", "📝 Paste Text", "📊 Results"])
    
    with tab1:
        st.subheader("Upload Your Document")
        
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=['txt', 'pdf', 'docx'],
            help="Upload a document to check for plagiarism"
        )
        
        if uploaded_file:
            st.success(f"✅ File uploaded: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
            
            if st.button("🔍 Check for Plagiarism", key="upload_check", type="primary"):
                with st.spinner("Loading document..."):
                    text = load_file(uploaded_file)
                
                if text and len(text.split()) >= 50:
                    st.info(f"📄 Document loaded: {len(text.split())} words")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    with st.spinner("Analyzing document..."):
                        results = check_plagiarism(text, max_phrases, progress_bar, status_text)
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    if results:
                        st.session_state.results = results
                        st.success("✅ Analysis complete! Check the Results tab.")
                        st.balloons()
                else:
                    st.error("❌ Document too short or could not be read. Minimum 50 words required.")
    
    with tab2:
        st.subheader("Paste Your Text")
        
        text_input = st.text_area(
            "Enter or paste your text here",
            height=300,
            placeholder="Paste your text here to check for plagiarism..."
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔍 Check Text", key="text_check", type="primary"):
                if text_input and len(text_input.split()) >= 50:
                    st.info(f"📄 Text loaded: {len(text_input.split())} words")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    with st.spinner("Analyzing text..."):
                        results = check_plagiarism(text_input, max_phrases, progress_bar, status_text)
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    if results:
                        st.session_state.results = results
                        st.success("✅ Analysis complete! Check the Results tab.")
                        st.balloons()
                else:
                    st.error("❌ Text too short. Minimum 50 words required.")
        
        with col2:
            word_count = len(text_input.split())
            st.metric("Word Count", word_count)
    
    with tab3:
        if st.session_state.results:
            results = st.session_state.results
            
            # Top metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"""
                <div class="metric-card">
                    <h2>{results['plagiarism_percentage']}%</h2>
                    <p>Plagiarism Score</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                <div class="metric-card">
                    <h2>{results['severity']}</h2>
                    <p>Risk Level</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                st.markdown(f"""
                <div class="metric-card">
                    <h2>{results['found_online']}</h2>
                    <p>Matches Found</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col4:
                st.markdown(f"""
                <div class="metric-card">
                    <h2>{len(results['sources'])}</h2>
                    <p>Sources</p>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Charts
            col1, col2 = st.columns(2)
            
            with col1:
                st.plotly_chart(
                    create_gauge_chart(results['plagiarism_percentage']),
                    use_container_width=True
                )
            
            with col2:
                st.plotly_chart(
                    create_pie_chart(results['found_online'], results['original']),
                    use_container_width=True
                )
            
            st.markdown("---")
            
            # Sources
            if results['sources']:
                st.subheader(f"🌐 Matching Sources ({len(results['sources'])})")
                
                for i, source in enumerate(results['sources'][:10], 1):
                    with st.expander(f"Source {i}: {source['title'][:80]}"):
                        st.markdown(f"**URL:** [{source['url']}]({source['url']})")
                        st.markdown(f"**Relevance:** {source.get('relevance', 'N/A')}%")
                        st.markdown(f"**Matched Phrases:** {len(source['phrases_matched'])}")
                        
                        if source['phrases_matched']:
                            st.markdown("**Sample matches:**")
                            for phrase in source['phrases_matched'][:3]:
                                st.markdown(f"- \"{phrase}...\"")
            
            st.markdown("---")
            
            # Flagged phrases
            flagged = [r for r in results['detailed_results'] if r['found']]
            if flagged:
                st.subheader(f"⚠️ Potentially Plagiarized Phrases ({len(flagged)})")
                
                for i, item in enumerate(flagged[:10], 1):
                    st.markdown(f"""
                    <div class="phrase-card">
                        <strong>{i}.</strong> "{item['phrase'][:100]}..."
                        <br><small>Found in {len(item['sources'])} source(s)</small>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Download report
            st.markdown("---")
            st.subheader("📥 Download Report")
            
            col1, col2 = st.columns(2)
            
            with col1:
                json_data = json.dumps(results, indent=2)
                st.download_button(
                    label="Download JSON Report",
                    data=json_data,
                    file_name=f"plagiarism_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
            
            with col2:
                # Create text report
                text_report = f"""
PLAGIARISM DETECTION REPORT
Generated: {results['timestamp']}
{'='*50}

SUMMARY
Plagiarism Score: {results['plagiarism_percentage']}%
Risk Level: {results['severity']}
Phrases Checked: {results['total_checked']}
Found Online: {results['found_online']}
Original: {results['original']}

SOURCES FOUND: {len(results['sources'])}
{'='*50}
"""
                for i, src in enumerate(results['sources'], 1):
                    text_report += f"\n{i}. {src['title']}\n   URL: {src['url']}\n   Matches: {len(src['phrases_matched'])}\n"
                
                st.download_button(
                    label="Download Text Report",
                    data=text_report,
                    file_name=f"plagiarism_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
        
        else:
            st.info("📊 No results yet. Upload a document or paste text to get started.")
            st.image("https://img.icons8.com/clouds/300/000000/search.png", width=200)

# ---------- RUN APP ----------
if __name__ == "__main__":
    main()
