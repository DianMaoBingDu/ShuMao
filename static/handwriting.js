class HandwritingBoard {
    constructor(options) {
        this.canvas = options.canvas;
        this.ctx = this.canvas.getContext('2d');
        this.onCandidatesUpdate = options.onCandidatesUpdate;
        this.inputElement = options.inputElement;

        this.isDrawing = false;
        this.strokes = [];
        this.currentStroke = [];
        this.lastTstamp = 0;
        this.lastPt = null;

        this.setupCanvas();
        this.drawGrid();
        this.bindEvents();
    }

    setupCanvas() {
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';
        this.ctx.lineWidth = 5;
        this.ctx.strokeStyle = '#4a4a4a';
    }

    drawGrid() {
        const w = this.canvas.width;
        const h = this.canvas.height;
        this.ctx.save();
        this.ctx.setLineDash([2, 4]);
        this.ctx.lineWidth = 0.5;
        this.ctx.strokeStyle = "#ccc";

        this.ctx.beginPath();
        // Border
        this.ctx.strokeRect(0, 0, w, h);

        // Diagonals
        this.ctx.moveTo(0, 0);
        this.ctx.lineTo(w, h);
        this.ctx.moveTo(w, 0);
        this.ctx.lineTo(0, h);

        // Midlines
        this.ctx.moveTo(w / 2, 0);
        this.ctx.lineTo(w / 2, h);
        this.ctx.moveTo(0, h / 2);
        this.ctx.lineTo(w, h / 2);

        this.ctx.stroke();
        this.ctx.restore();
    }

    bindEvents() {
        const startDrawing = (e) => {
            this.isDrawing = true;
            this.currentStroke = [];
            const pos = this.getPointerPos(e);
            this.lastPt = [pos.x, pos.y];
            this.lastTstamp = Date.now();
            this.addPoint(pos.x, pos.y);

            this.ctx.beginPath();
            this.ctx.lineWidth = 5;
            this.ctx.strokeStyle = '#4a4a4a';
            this.ctx.setLineDash([]);
            this.ctx.moveTo(pos.x, pos.y);
        };

        const draw = (e) => {
            if (!this.isDrawing) return;

            const now = Date.now();
            if (now - this.lastTstamp < 30) return; // Throttle points
            this.lastTstamp = now;

            const pos = this.getPointerPos(e);
            if (this.lastPt && pos.x === this.lastPt[0] && pos.y === this.lastPt[1]) return;

            this.addPoint(pos.x, pos.y);
            this.lastPt = [pos.x, pos.y];

            this.ctx.lineTo(pos.x, pos.y);
            this.ctx.stroke();
        };

        const stopDrawing = (e) => {
            if (!this.isDrawing) return;
            this.isDrawing = false;

            // Add final point
            if (e) {
                const pos = this.getPointerPos(e);
                this.addPoint(pos.x, pos.y);
                this.ctx.lineTo(pos.x, pos.y);
                this.ctx.stroke();
            }

            this.strokes.push(this.currentStroke);
            this.lookup();
        };

        this.canvas.addEventListener('mousedown', startDrawing);
        this.canvas.addEventListener('mousemove', draw);
        window.addEventListener('mouseup', stopDrawing);

        this.canvas.addEventListener('touchstart', (e) => {
            e.preventDefault();
            startDrawing(e.touches[0]);
        }, { passive: false });
        this.canvas.addEventListener('touchmove', (e) => {
            e.preventDefault();
            draw(e.touches[0]);
        }, { passive: false });
        this.canvas.addEventListener('touchend', (e) => {
            e.preventDefault();
            stopDrawing(e.changedTouches[0]);
        }, { passive: false });
    }

    getPointerPos(e) {
        const rect = this.canvas.getBoundingClientRect();
        // Calculate position relative to canvas coordinate space
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        return {
            x: (e.clientX - rect.left) * scaleX,
            y: (e.clientY - rect.top) * scaleY
        };
    }

    addPoint(x, y) {
        this.currentStroke.push([x, y]);
    }

    clear() {
        this.strokes = [];
        this.currentStroke = [];
        this.redraw();
        if (this.onCandidatesUpdate) {
            this.onCandidatesUpdate([]);
        }
    }

    undo() {
        if (this.strokes.length === 0) return;
        this.strokes.pop();
        this.redraw();
        this.lookup();
    }

    redraw() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.drawGrid();

        this.ctx.save();
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';
        this.ctx.lineWidth = 5;
        this.ctx.strokeStyle = '#4a4a4a';
        this.ctx.setLineDash([]);

        this.strokes.forEach(stroke => {
            if (stroke.length < 1) return;
            this.ctx.beginPath();
            this.ctx.moveTo(stroke[0][0], stroke[0][1]);
            stroke.forEach(point => {
                this.ctx.lineTo(point[0], point[1]);
            });
            this.ctx.stroke();
        });
        this.ctx.restore();
    }

    lookup() {
        if (this.strokes.length === 0) {
            if (this.onCandidatesUpdate) this.onCandidatesUpdate([]);
            return;
        }

        // Normalize strokes to 256x256 for the engine
        const normalizedStrokes = this.strokes.map(stroke =>
            stroke.map(point => [
                Math.round(point[0] * 256 / this.canvas.width),
                Math.round(point[1] * 256 / this.canvas.height)
            ])
        );

        if (window.wasm_bindgen && typeof wasm_bindgen.lookup === 'function') {
            try {
                // The library expects an array of strokes, where each stroke is an array of points [x, y]
                const resultJson = wasm_bindgen.lookup(normalizedStrokes, 12);
                const candidates = JSON.parse(resultJson);
                if (this.onCandidatesUpdate) {
                    this.onCandidatesUpdate(candidates);
                }
            } catch (err) {
                console.error("Lookup error:", err);
            }
        }
    }
}

// Global initialization helper
function initHandwriting(containerId, inputId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const canvas = container.querySelector('canvas');
    const candidatesArea = container.querySelector('.handwriting-candidates');
    const input = document.getElementById(inputId);
    const clearBtn = container.querySelector('.clear-btn');
    const undoBtn = container.querySelector('.undo-btn');

    const board = new HandwritingBoard({
        canvas: canvas,
        inputElement: input,
        onCandidatesUpdate: (candidates) => {
            candidatesArea.innerHTML = '';
            candidates.forEach(c => {
                const btn = document.createElement('button');
                btn.className = 'candidate-item';
                btn.textContent = c.hanzi;
                btn.onclick = () => {
                    input.value += c.hanzi;
                    board.clear();
                    // Optionally trigger search or focus input
                    input.focus();
                };
                candidatesArea.appendChild(btn);
            });
        }
    });

    if (clearBtn) clearBtn.onclick = () => board.clear();
    if (undoBtn) undoBtn.onclick = () => board.undo();

    return board;
}
