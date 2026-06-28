import uvicorn

if __name__ == "__main__":
    uvicorn.run("data_analysis.api:app", host="0.0.0.0", port=8001, reload=False)
