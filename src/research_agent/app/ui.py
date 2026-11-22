"""Streamlit workspace for local technical research."""

import os

import requests
import streamlit as st

API_URL = os.getenv("RESEARCH_API_URL", "http://127.0.0.1:8000").rstrip("/")
STATUS = {"queued": "排队中", "running": "执行中", "completed": "已完成", "partial": "部分完成",
          "failed": "失败", "interrupted": "已中断", "pending": "待执行", "succeeded": "完成", "blocked": "阻塞"}


def request(method: str, path: str, **kwargs):
    response = requests.request(method, f"{API_URL}{path}", timeout=10, **kwargs)
    if response.ok:
        return response
    try:
        detail = response.json()["detail"]
    except (ValueError, KeyError):
        detail = "本机 API 返回错误"
    raise ValueError(detail if isinstance(detail, str) else "请求参数无效")


@st.fragment(run_every="3s")
def show_run(job_id: str) -> None:
    try:
        item = request("GET", f"/jobs/{job_id}").json()
    except (requests.RequestException, ValueError) as error:
        st.error(f"无法读取任务 · {error}")
        return
    with st.chat_message("user"):
        st.text(item["topic"])
    tasks = item["tasks"]
    completed = sum(task["status"] == "succeeded" for task in tasks)
    with st.container(border=True):
        columns = st.columns(3)
        columns[0].metric("任务状态", STATUS[item["status"]])
        columns[1].metric("完成步骤", f"{completed} / {len(tasks)}")
        columns[2].metric("资料文件", len(item["documents"]))
        if tasks:
            st.dataframe([{"研究问题": task["question"], "状态": STATUS[task["status"]],
                           "尝试": task["attempts"], "说明": task["error"] or ""}
                          for task in tasks], hide_index=True)
        elif item["status"] in {"queued", "running"}:
            st.caption("正在等待研究计划。")
        if item["documents"]:
            st.caption("资料 · " + "、".join(doc["name"] for doc in item["documents"]))
    if item["tools"]:
        with st.expander("工具调用记录"):
            st.dataframe([{"工具": event["tool"], "结果": "成功" if event["ok"] else "失败",
                           "说明": event["detail"]} for event in item["tools"]], hide_index=True)
    if item["error"]:
        st.error(item["error"])
    if item["status"] == "interrupted" and st.button("继续执行"):
        try:
            request("POST", f"/jobs/{job_id}/resume")
        except (requests.RequestException, ValueError) as error:
            st.error(str(error))
        else:
            st.rerun()
    if item["report_ready"]:
        try:
            markdown = request("GET", f"/jobs/{job_id}/report").text
        except (requests.RequestException, ValueError) as error:
            st.error(f"无法读取报告 · {error}")
        else:
            with st.chat_message("assistant"):
                st.download_button("下载 Markdown", markdown, file_name=f"research-{job_id[:8]}.md",
                                   mime="text/markdown", on_click="ignore")
                st.markdown(markdown)


def main() -> None:
    st.set_page_config(page_title="Research Agent", page_icon="📖", layout="wide")
    st.html("""
        <style>
        .block-container { max-width: 1120px; padding-top: 2.35rem; }
        [data-testid=stMetricValue] { font-variant-numeric: tabular-nums; }
        </style>
    """)
    st.title("Research Agent")
    st.caption("使用本地资料或维基百科，生成带可追溯引用的研究报告。")
    try:
        jobs = request("GET", "/jobs").json()
    except (requests.RequestException, ValueError) as error:
        st.error(f"无法连接研究服务 · {error}")
        st.button("重新连接")
        return

    st.sidebar.header("研究历史")
    st.sidebar.button("刷新历史")
    choices = {job["id"]: job["topic"] for job in jobs}
    available = [None, *choices]
    current = st.session_state.get("active_job")
    selected = st.sidebar.selectbox("查看任务", available,
                                   index=available.index(current) if current in available else 0,
                                   format_func=lambda key: choices[key] if key else "新建研究")
    if selected:
        show_run(selected)

    with st.expander("研究资料", expanded=selected is None):
        upload_round = st.session_state.get("upload_round", 0)
        files = st.file_uploader("上传 PDF、TXT 或 Markdown", type=["pdf", "txt", "md"],
                                 accept_multiple_files=True, key=f"documents-{upload_round}")
        online = st.checkbox("允许向英文维基百科发送搜索词")
        query = st.text_input("搜索词（可选）", max_chars=256) if online else ""
        reuse_documents = bool(selected and st.checkbox("沿用当前任务的已上传资料", key=f"reuse-{selected}"))
        include_topic = bool(selected and st.checkbox("把上一轮问题作为背景", key=f"context-{selected}"))
    if topic := st.chat_input("输入一个技术研究问题", max_chars=300):
        if len(files) > 8 or sum(file.size for file in files) > 32 * 1024 * 1024:
            st.error("每个任务最多 8 份文件，合计不超过 32 MiB。")
            return
        if any(file.size > 12 * 1024 * 1024 for file in files):
            st.error("每份文件最大为 12 MiB。")
            return
        try:
            document_ids = [
                request("POST", "/documents", params={"name": file.name}, data=file.getvalue(),
                        headers={"Content-Type": "application/octet-stream"}).json()["id"]
                for file in files
            ]
            job = request("POST", "/jobs", json={"topic": topic, "documents": document_ids, "online": online,
                                                "query": query.strip() or None,
                                                "parent_id": selected if reuse_documents or include_topic else None,
                                                "reuse_documents": reuse_documents,
                                                "include_previous_topic": include_topic}).json()
        except (requests.RequestException, ValueError) as error:
            st.error(f"无法提交任务 · {error}")
        else:
            st.session_state.active_job = job["id"]
            st.session_state.upload_round = upload_round + 1
            st.rerun()


if __name__ == "__main__":
    main()
