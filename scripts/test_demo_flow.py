import json
import shutil
from pathlib import Path
from app.config.settings import Settings
from app.edge.client import EdgeClient
from app.edge.collection import initialize_experience_collection
from app.edge.repository import ExperienceRepository
from app.embeddings.service import get_embedding_service
from app.embeddings.bm25 import get_bm25_service
from app.ingestion.seed import seed_database
from app.memory.repository import MemoryRepository
from app.memory.service import UserMemoryService

tmp_dir = Path("tmp_test_demo")
if tmp_dir.exists():
    shutil.rmtree(tmp_dir)
tmp_dir.mkdir(exist_ok=True)
edge_dir = tmp_dir / "edge"
mem_file = tmp_dir / "mem.db"

settings = Settings(
    edge_storage_path=edge_dir,
    sqlite_db_path=str(mem_file),
    collection_name="demo_test_col",
    seed_data_path=Path("data/seed/experiences.json"),
    auto_seed_on_startup=False,
)

client = EdgeClient(settings.edge_storage_path)
shard = initialize_experience_collection(client, settings)
emb_service = get_embedding_service(settings.embedding_model_name, settings.embedding_dimension)
bm25_service = get_bm25_service()
repo = ExperienceRepository(shard, client, settings)

seed_database(repo, settings, embedding_service=emb_service, overwrite=True)

mem_repo = MemoryRepository(str(mem_file))
mem_svc = UserMemoryService(mem_repo, repo)

query = "adventurous and thrilling"
dense_vec = emb_service.embed_text(query)
sparse_vec = bm25_service.embed_query(query)

unpersonalized_results, timings = repo.search_hybrid(
    query_vector=dense_vec,
    sparse_vector=sparse_vec,
    dense_top_k=20,
    bm25_top_k=20,
    final_top_k=10,
    rrf_k=60,
)

print(f"=== UNPERSONALIZED SEARCH FOR: '{query}' ===")
for rank_idx, r in enumerate(unpersonalized_results[:6], 1):
    print(f"Rank {rank_idx}: {r.title} ({r.category}) - RRF: {r.score:.5f}")

# User saves horror items: Bhangarh Horror Mystery Room, The Vvaan, Hereditary & Tumbbad
mem_svc.add_bookmark("demo-user", 11) # Bhangarh Horror Mystery Room
mem_svc.add_bookmark("demo-user", 3)  # The Vvaan - Force of the Forrest
mem_svc.add_bookmark("demo-user", 6)  # Hereditary & Tumbbad

profile = mem_svc.get_user_preferences("demo-user")
print(f"\nLearned Profile subcategories: {profile.preferred_subcategories}")

# Personalized re-ranking
personalized_results, meta = mem_svc.personalize_results("demo-user", unpersonalized_results)
print(f"\n=== PERSONALIZED SEARCH FOR: '{query}' ===")
for rank_idx, r in enumerate(personalized_results[:6], 1):
    print(f"Rank {rank_idx}: {r.title} ({r.category}) - Score: {r.score:.5f}")

client.close()
mem_repo.close()
shutil.rmtree(tmp_dir)
