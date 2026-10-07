# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Neo4j Startup Guide

To run ContextGraph RAG and persist entities/relations into Neo4j:

### Option 1: Using the Startup Script (Recommended)

From the project root directory, run:

```powershell
.\start_neo4j.bat
# or in PowerShell:
.\start_neo4j.ps1
```

Or run the full application launcher which starts Neo4j, FastAPI, and Streamlit together:

```cmd
run_project.bat
```

### Option 2: Using Neo4j Desktop UI

1. Open **Neo4j Desktop** (installed at `C:\Users\HemantMore\AppData\Local\Programs\Neo4j Desktop 2`).
2. Find the project and click **Start** on the database instance.
3. The database will listen on `bolt://localhost:7687` (HTTP browser on `http://localhost:7474`).

### Connection Details (`.env`):
- **URI:** `bolt://localhost:7687`
- **Username:** `neo4j`
- **Password:** `contextgraph` (or auth disabled locally)
- **Database:** `neo4j`
