\# Known retrieval failures (RepoMind, Day 3)



Measured on 12 hand-written questions about the researchpilot repo

(45 files, 176 chunks). Models compared: all-MiniLM-L6-v2, bge-small-en-v1.5,

and the jina code model. Default model: bge-small-en-v1.5 with hybrid search.



\## c04: "Where are chunks turned into vectors?"

\- Expected file: backend/app/embeddings.py

\- All three models miss the top 3 in hybrid search.

\- With bge-small the top 3 were vector\_store.py, chunking.py and tests/conftest.py.

\- Possible cause (not verified): embeddings.py is a very small file, and other

&#x20; files use the words "chunks" and "vectors" more often than it does.



\## c09: "Where is each answer's status (answered, unverified, and so on) decided?"

\- Expected file: backend/app/rag.py

\- With MiniLM, hybrid ranks other files above it: StatusBadge.jsx,

&#x20; eval/known\_failures.md and tests/test\_ask.py.

\- bge-small and the jina model do not miss this one in the top 3.

\- Before the JSON filter, large result files (eval/results\_\*.json) took the top

&#x20; places. Skipping .json files over 5 KB fixed that part.



\## Ideas to try later (not tested yet)

\- Lower the score of test files for "where is X implemented" questions.

\- Check whether a longer label in front of each chunk helps small files.

\- Add more questions: 12 is too few to trust differences of one question.

