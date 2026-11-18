# this is a justfile, why remember packages when you can just add them here!


# recipies:
test-run:
	echo 'Just just... works!'

setup-nltk:
	uv run python -m nltk.downloader stopwords

# Download and cache the sentence-embedding model used for keyword analysis.
download-model:
	uv run python -c "from cs122_final_project import embeddings; print(embeddings.model_name(), embeddings.embedding_dim())"

# Cache sentence embeddings for every stored keyword.
embed-keywords:
	uv run python manage.py embed_keywords

# Remove a video and its collected data so it can be collected again.
reset-video url:
	cd src && uv run python -c 'import sys; from cs122_final_project.collector import extract_video_id; from cs122_final_project.database import Database; video_id = extract_video_id(sys.argv[1]); db = Database(); db.initialize(); db.delete_video(video_id); db.close(); print(f"Deleted collected data for {video_id}")' "{{url}}"

# Run the complete collector pipeline against a YouTube URL.
# The video is reset first so every run exercises the full pipeline.
test-collector url="https://www.youtube.com/watch?v=Ks-_Mh1QhMc": (reset-video url)
	cd src && echo "{{url}}" | uv run python -m cs122_final_project.collector
