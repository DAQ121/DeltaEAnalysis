from flask import Flask, request, jsonify
from flask_cors import CORS
from image_processor import analyze_image

app = Flask(__name__)
CORS(app)


@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        image_data = data.get('image')
        threshold = data.get('threshold', 10)
        grid_size = data.get('grid_size', 20)
        reference_ratio = data.get('reference_ratio', 0.15)

        result = analyze_image(image_data, threshold, grid_size, reference_ratio)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
