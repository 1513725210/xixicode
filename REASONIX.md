# Reasonix project memory

Notes the user pinned via the `#` prompt prefix. The whole file is
loaded into the immutable system prefix every session — keep it terse.

- Reasonix project memory

Notes the user pinned via the `#` prompt prefix. The whole file is
loaded into the immutable system prefix every session — keep it terse.

- MiniCode Specification

Version: v1.0

Author: Deng Xiaoyi

Status: Draft

---

# 1. Project Overview

## 1.1 Vision

MiniCode 是一个面向本地代码仓库的 AI Coding Agent。

系统参考 Claude Code 架构设计，通过 Query Loop + Tool Use 实现自主任务执行能力。

目标并非构建聊天机器人，而是构建能够：

* 理解代码库
* 制定执行计划
* 调用工具
* 修改代码
* 运行测试
* 总结经验
* 持续进化

的工程级 Coding Agent。

---

# 2. Design Principles

## Principle 1

Agent First

所有功能围绕 Agent 构建。

禁止：

User -> Tool

必须：

User -> Agent -> Tool

---

## Principle 2

Memory Driven

Agent 必须具备长期记忆能力。

任何执行结果都应有机会沉淀为记忆资产。

---

## Principle 3

Skill Oriented

Agent 不直接学习 Tool。

Agent 学习 Skill。

Skill 再组合 Tool。

---

## Principle 4

Safe Execution

所有危险操作必须经过审查。

---

# 3. MVP Scope

V1 不实现：

* GUI
* Browser Agent
* Voice
* Remote Execution

仅支持：

* Local Repository
* CLI
* Tool Calling
* Memory
* Skill
* Reflection

---

# 4. System Architecture

User

↓

Main Agent

↓

Planner

↓

Skill Router

↓

Skill Executor

↓

Tool Layer

↓

Memory Layer

↓

Reflection Layer

---

# 5. Core Workflow

## Query Loop

Agent 持续运行以下循环：

1. Understand Task

2. Plan

3. Select Skill

4. Execute Tool

5. Observe Result

6. Update Context

7. Determine Completion

8. Reflect

---

Pseudo Code

while not task_completed:

think()

select_skill()

execute()

observe()

update_context()

---

# 6. Agent Architecture

## Main Agent

职责：

* 理解用户需求
* 管理上下文
* 规划任务
* 调度 Skill
* 判断任务完成

输入：

Task

输出：

Execution Plan

---

## Planner Agent

职责：

任务拆解

Example

User:

Fix order service NPE

Output:

Step1 Read Logs

Step2 Locate Source

Step3 Root Cause

Step4 Fix

Step5 Test

---

## Reflection Agent

职责：

任务结束后总结经验

输出：

Procedural Memory

Episodic Memory

Knowledge Memory

---

# 7. Skill System

## Objective

解决 Tool 数量增长导致选择困难问题

---

Skill

= Reusable Capability

---

Example

Bug Fix Skill

Refactor Skill

Test Skill

Code Review Skill

Dependency Analysis Skill

---

# 8. Skill Metadata

{
"name": "bug_fix",

"description": "...",

"tags": [
"java",
"spring",
"exception"
],

"examples": [
"NPE",
"OOM"
],

"boundary": "...",

"tool_requirements": [
"read_file",
"grep",
"edit_file"
]
}

---

# 9. Skill Routing

## Stage 1

Embedding Recall

Top K = 20

---

## Stage 2

LLM Rerank

Top K = 5

---

Output

Selected Skill

Confidence Score

---

# 10. Tool System

## Tool Interface

class Tool:

name:str

description:str

parameters:dict

execute()

---

V1 Tools

ReadFile

WriteFile

EditFile

SearchFile

Grep

RunCommand

GitStatus

GitDiff

RunTest

---

# 11. Memory System

Memory Layer

├── User Memory

├── Episodic Memory

├── Procedural Memory

└── Knowledge Memory

---

## User Memory

长期用户偏好

Example

Preferred Language = Java

---

## Episodic Memory

任务执行历史

Example

Fixed OrderService NPE

---

## Procedural Memory

经验总结

Example

NPE -> check DTO mapping first

---

## Knowledge Memory

知识资产

Example

Project Architecture Summary

---

# 12. Memory Storage

Metadata

Content

Embedding

Timestamp

Importance Score

Access Count

---

Storage

ChromaDB

---

# 13. Reflection Pipeline

Task Finished

↓

Reflection

↓

Extract Lessons

↓

Categorize

↓

Store

↓

Update Index

---

Prompt

What worked?

What failed?

Can this be reused?

Should a new skill be created?

---

# 14. Context Management

Problem

Context Window Overflow

---

Solution

Hierarchical Compression

---

Level 1

Short Summary

<100 tokens

---

Level 2

Detailed Summary

<500 tokens

---

Level 3

Raw Content

External Storage

---

# 15. Prompt Cache

Cache Key

Task

Skill

Repository

Memory Snapshot

---

Hit Strategy

Semantic Similarity

Threshold > 0.9

---

# 16. Multi-Agent Design

Architecture

Main Agent

↓

Sub Agent

↓

Tool

---

Rules

Sub Agent cannot call another Sub Agent

Sub Agent cannot modify global state

Sub Agent only returns results

Main Agent owns final decision

---

# 17. Security Layer

Level 1

Rule Check

Block:

rm -rf

sudo

shutdown

---

Level 2

Prompt Injection Detection

Detect:

ignore instruction

system prompt leak

credential extraction

---

Level 3

Risk Classification

SAFE

MEDIUM

HIGH

---

Level 4

Human Approval

Required for:

git push

mass edit

file deletion

---

# 18. Observability

Trace Every Step

Task

Skill

Tool

Memory

Reflection

---

Metrics

Success Rate

Tool Call Count

Skill Recall Accuracy

Memory Hit Rate

Average Tokens

Execution Time

---

# 19. Tech Stack

Framework

LangGraph

---

LLM

Claude

GPT

Qwen

---

Memory

ChromaDB

---

Cache

Redis

---

Runtime

Python

---

Sandbox

Docker

---

Observability

LangSmith

OpenTelemetry

---

# 20. Roadmap

V1

Single Agent

Skill

Memory

Tool

Reflection

---

V2

Context Compression

Prompt Cache

Observability

---

V3

Multi Agent

Worktree

Parallel Execution

---

V4

Self Evolving Skill Generation

Automatic Skill Discovery
这是我准备的spec，先创建一个spec.md文件，我现在想做一个minicode，供个人使用的轻量级多协同agent，先讨论这个spec，并且任何改动都保存到这个spec里，并且在开发时，要先写好测试用例，现在先不开发代码，讨论技术选型和思路
- MiniCode Specification

Version: v1.0

Author: Deng Xiaoyi

Status: Draft

---

# 1. Project Overview

## 1.1 Vision

MiniCode 是一个面向本地代码仓库的 AI Coding Agent。

系统参考 Claude Code 架构设计，通过 Query Loop + Tool Use 实现自主任务执行能力。

目标并非构建聊天机器人，而是构建能够：

* 理解代码库
* 制定执行计划
* 调用工具
* 修改代码
* 运行测试
* 总结经验
* 持续进化

的工程级 Coding Agent。

---

# 2. Design Principles

## Principle 1

Agent First

所有功能围绕 Agent 构建。

禁止：

User -> Tool

必须：

User -> Agent -> Tool

---

## Principle 2

Memory Driven

Agent 必须具备长期记忆能力。

任何执行结果都应有机会沉淀为记忆资产。

---

## Principle 3

Skill Oriented

Agent 不直接学习 Tool。

Agent 学习 Skill。

Skill 再组合 Tool。

---

## Principle 4

Safe Execution

所有危险操作必须经过审查。

---

# 3. MVP Scope

V1 不实现：

* GUI
* Browser Agent
* Voice
* Remote Execution

仅支持：

* Local Repository
* CLI
* Tool Calling
* Memory
* Skill
* Reflection

---

# 4. System Architecture

User

↓

Main Agent

↓

Planner

↓

Skill Router

↓

Skill Executor

↓

Tool Layer

↓

Memory Layer

↓

Reflection Layer

---

# 5. Core Workflow

## Query Loop

Agent 持续运行以下循环：

1. Understand Task

2. Plan

3. Select Skill

4. Execute Tool

5. Observe Result

6. Update Context

7. Determine Completion

8. Reflect

---

Pseudo Code

while not task_completed:

think()

select_skill()

execute()

observe()

update_context()

---

# 6. Agent Architecture

## Main Agent

职责：

* 理解用户需求
* 管理上下文
* 规划任务
* 调度 Skill
* 判断任务完成

输入：

Task

输出：

Execution Plan

---

## Planner Agent

职责：

任务拆解

Example

User:

Fix order service NPE

Output:

Step1 Read Logs

Step2 Locate Source

Step3 Root Cause

Step4 Fix

Step5 Test

---

## Reflection Agent

职责：

任务结束后总结经验

输出：

Procedural Memory

Episodic Memory

Knowledge Memory

---

# 7. Skill System

## Objective

解决 Tool 数量增长导致选择困难问题

---

Skill

= Reusable Capability

---

Example

Bug Fix Skill

Refactor Skill

Test Skill

Code Review Skill

Dependency Analysis Skill

---

# 8. Skill Metadata

{
"name": "bug_fix",

"description": "...",

"tags": [
"java",
"spring",
"exception"
],

"examples": [
"NPE",
"OOM"
],

"boundary": "...",

"tool_requirements": [
"read_file",
"grep",
"edit_file"
]
}

---

# 9. Skill Routing

## Stage 1

Embedding Recall

Top K = 20

---

## Stage 2

LLM Rerank

Top K = 5

---

Output

Selected Skill

Confidence Score

---

# 10. Tool System

## Tool Interface

class Tool:

name:str

description:str

parameters:dict

execute()

---

V1 Tools

ReadFile

WriteFile

EditFile

SearchFile

Grep

RunCommand

GitStatus

GitDiff

RunTest

---

# 11. Memory System

Memory Layer

├── User Memory

├── Episodic Memory

├── Procedural Memory

└── Knowledge Memory

---

## User Memory

长期用户偏好

Example

Preferred Language = Java

---

## Episodic Memory

任务执行历史

Example

Fixed OrderService NPE

---

## Procedural Memory

经验总结

Example

NPE -> check DTO mapping first

---

## Knowledge Memory

知识资产

Example

Project Architecture Summary

---

# 12. Memory Storage

Metadata

Content

Embedding

Timestamp

Importance Score

Access Count

---

Storage

ChromaDB

---

# 13. Reflection Pipeline

Task Finished

↓

Reflection

↓

Extract Lessons

↓

Categorize

↓

Store

↓

Update Index

---

Prompt

What worked?

What failed?

Can this be reused?

Should a new skill be created?

---

# 14. Context Management

Problem

Context Window Overflow

---

Solution

Hierarchical Compression

---

Level 1

Short Summary

<100 tokens

---

Level 2

Detailed Summary

<500 tokens

---

Level 3

Raw Content

External Storage

---

# 15. Prompt Cache

Cache Key

Task

Skill

Repository

Memory Snapshot

---

Hit Strategy

Semantic Similarity

Threshold > 0.9

---

# 16. Multi-Agent Design

Architecture

Main Agent

↓

Sub Agent

↓

Tool

---

Rules

Sub Agent cannot call another Sub Agent

Sub Agent cannot modify global state

Sub Agent only returns results

Main Agent owns final decision

---

# 17. Security Layer

Level 1

Rule Check

Block:

rm -rf

sudo

shutdown

---

Level 2

Prompt Injection Detection

Detect:

ignore instruction

system prompt leak

credential extraction

---

Level 3

Risk Classification

SAFE

MEDIUM

HIGH

---

Level 4

Human Approval

Required for:

git push

mass edit

file deletion

---

# 18. Observability

Trace Every Step

Task

Skill

Tool

Memory

Reflection

---

Metrics

Success Rate

Tool Call Count

Skill Recall Accuracy

Memory Hit Rate

Average Tokens

Execution Time

---

# 19. Tech Stack

Framework

LangGraph

---

LLM

Claude

GPT

Qwen

---

Memory

ChromaDB

---

Cache

Redis

---

Runtime

Python

---

Sandbox

Docker

---

Observability

LangSmith

OpenTelemetry

---

# 20. Roadmap

V1

Single Agent

Skill

Memory

Tool

Reflection

---

V2

Context Compression

Prompt Cache

Observability

---

V3

Multi Agent

Worktree

Parallel Execution

---

V4

Self Evolving Skill Generation

Automatic Skill Discovery

现在当前路径创建一个spec.md，我想做一个minicode，供个人使用的本地代码agent，上面是我想要的技术选型。写代码的同时写好测试用例。
- Reasonix project memory
