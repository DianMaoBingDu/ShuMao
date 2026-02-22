import sqlite3
import os

def export_dict():
    db_path = os.path.join(os.path.dirname(__file__), 'resources', 'dictionary.db')
    out_path = os.path.join(os.path.dirname(__file__), 'resources', 'jieba_custom_dict.txt')
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # We want to extract all simplified and traditional words
    words = set()
    cur.execute("SELECT simplified, traditional FROM dictionary")
    for row in cur.fetchall():
        simplified, traditional = row
        if simplified:
            words.add(simplified.strip())
        if traditional:
            words.add(traditional.strip())
            
    conn.close()
    
    # Write to custom dict file
    with open(out_path, 'w', encoding='utf-8') as f:
        for word in sorted(list(words)):
            if word:
                # jieba full dict format requires word, freq, and pos
                # We'll assign a default frequency of 100 and pos 'n'
                f.write(f"{word} 100 n\n")
                
    print(f"Exported {len(words)} words to {out_path}")

if __name__ == '__main__':
    export_dict()
