### Container Build Requirements

⚠️ **CRITICAL: COMMIT AND PUSH BEFORE BUILDING** ⚠️

**The jobforge service builds from the git repository, NOT from local files. All changes MUST be committed and pushed before triggering builds, or the build will use old versions of your files.**

**PRE-BUILD CHECKLIST:**
1. ✅ **COMMIT ALL CHANGES**: `git add .` and `git commit -m "..."`
2. ✅ **PUSH TO REMOTE**: `git push origin main`
3. ✅ **VERIFY PUSH**: Check that changes appear on GitHub
4. ✅ **THEN BUILD**: Use MCP build service

**Build When These Change:**
- **ALWAYS trigger a new container build** when making changes that affect the Docker container:
  - Changes to `docker/app/main.py` (container application code)
  - Changes to `docker/Dockerfile` or `docker/requirements.txt`
  - Environment variable handling changes in the container

**Cache Issues:**
- Docker cache is extremely persistent across builds
- If changes don't appear, add cache-busting comments to Dockerfile
- Consider changing file content (not just comments) to force cache invalidation


