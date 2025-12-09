# LLM Gamer Agent

LLM Gamer Agent は、Gemini を活用し、コンピュータ画面上の情報を視覚的に認識しながら、自律的にタスクを実行したりゲームをプレイしたりするエージェントシステムです。

Model Context Protocol (MCP) アーキテクチャを採用しており、エージェント自身が必要に応じて Python スクリプト（MCPサーバー）を作成・実行し、能力を拡張していくことができます。

## 特徴

*   **Gemini Native**: Gemini API を使用し、高速な応答と強力なマルチモーダル処理を実現。Native Function Calling 機能により、安定したツール実行が可能です。
*   **視覚的認識 (Vision)**: 画面のスクリーンショットをリアルタイムで取得・解析し、状況を把握します。
*   **自律的なツール作成 (Self-Coding)**: タスク達成のために必要なツール（Pythonコード）をエージェント自身が生成し、即座に実行環境にデプロイして使用します。
*   **マルチエージェントパイプライン**: 4つの専門エージェントが役割分担して協調動作し、複雑なタスクに対応します。
*   **リアルタイムダッシュボード (Live GUI)**: エージェントの視界、思考、記憶、実行ログをWebブラウザ上でリアルタイムに監視できるモダンなGUIを提供します。
*   **中断と再開 (Resumability)**: 過去の履歴からエージェントの状態を復元し、タスクを再開することができます。
*   **カテゴリ別記憶管理 (Memory)**: 重要な情報を目的別に分類して記憶し、各エージェントに適切な情報を提供します。

## アーキテクチャ

### マルチエージェントパイプライン

このシステムは、**4つの専門エージェント**が毎ターン順番に実行される固定パイプライン構造を採用しています。

```
[Screenshot取得] → [MemorySaver] → [ToolCreator] → [ResourceCleaner] → [Operator] → [Checkpoint保存]
```

| 役割 | 名前 | 責務 | アクセス可能なメモリ | 最大ステップ |
|------|------|------|----------------------|--------------|
| 📝 | **MemorySaver** | 前回の行動結果を評価し、重要な情報を記憶に保存 | Global, Engineering, Operation | 1 |
| 🔧 | **ToolCreator** | 必要なツール（MCPサーバー）の作成・修正 | Global, Engineering | 5 |
| 🗑️ | **ResourceCleaner** | 不要なメモリやツールの削除・整理 | Global, Engineering, Operation | 2 |
| 🎮 | **Operator** | 実際のゲーム操作・タスク実行 | Global, Operation | 1 |

### カテゴリ別記憶管理

メモリは3つのカテゴリに分類され、各エージェントは担当するカテゴリのみにアクセスします。

| カテゴリ | 用途 | 例 |
|----------|------|-----|
| **Global** | 全体目標、ルール、マイルストーン | "Ultimate Goal: Beat the boss" |
| **Engineering** | 技術情報、コードスニペット、ツールのバグ | "pyautogui click requires int coords" |
| **Operation** | ゲーム状態、座標、パターン情報 | "Boss HP bar location: (100, 50)" |

### ツール権限

各エージェントは、役割に応じたツールのみを使用できます：

*   **MemorySaver**: `memory_manager` のみ
*   **ToolCreator**: `meta_manager` (delete以外)
*   **ResourceCleaner**: `memory_manager.delete_memory`, `meta_manager.delete_mcp_server`, `meta_manager.list_mcp_files`
*   **Operator**: ユーザー作成ツールのみ (meta_manager, memory_manager 以外)

## 動作環境

*   **OS**: Windows (推奨)
*   **Python**: 3.10 以上
*   **LLM**: Google Gemini API Key

## インストール

1.  プロジェクトのルートディレクトリに移動します。

2.  仮想環境を作成し、有効化することを推奨します。
    ```bash
    python -m venv .venv
    .venv\Scripts\activate
    ```

3.  依存ライブラリをインストールします。
    ```bash
    pip install -r requirements.txt
    ```

4.  環境変数を設定します。
    `.env.example` をコピーして `.env` という名前のファイルを作成し、APIキーを設定してください。

    ```ini
    API_KEY=your_gemini_api_key_here
    GEMINI_MODEL=gemini-3-pro-preview
    ```

## 使い方

### エージェントの起動

以下のバッチファイルを実行するだけで、エージェントとダッシュボードが起動します。

```bash
./run.bat
```

または、Pythonコマンドで直接起動することも可能です。

```bash
python agent.py
```

※ 過去の実行履歴が見つかった場合、ダッシュボード上で「再開 (Resume)」するか「新規開始 (Start Fresh)」するかを選択するポップアップが表示されます。

### ダッシュボードへのアクセス

エージェント起動後、Webブラウザで以下のURLにアクセスしてください。

**URL**: [http://localhost:15000](http://localhost:15000)

ダッシュボードの機能：
*   **Live Vision**: エージェントが見ている現在の画面。
*   **Active Memories**: カテゴリ別に整理された現在のメモリ。
*   **Cognitive Stream**: 各エージェントの思考内容。
*   **Tool Activity**: 実行されたツールとその結果のログ。
*   **User Input**: エージェントからの質問や、タスクの指示入力画面。

## 使用可能なライブラリ

エージェントが自律的にツール（Pythonスクリプト）を作成する際、以下のライブラリを使用するように制限・推奨されています。これにより、安全かつ効率的なコード生成を促します。

*   **基本操作**: `time`, `json`, `re` 等の標準ライブラリ
*   **画面操作**: `pyautogui`, `pydirectinput` (ゲーム用), `pygetwindow`
*   **画像認識**: `easyocr` (OCR), `pillow`, `cv2` (OpenCV), `mss` (高速キャプチャ), `numpy`
*   **システム**: `psutil`, `pyperclip`, `pywin32`

## ディレクトリ構成

```
llmgamer/
├── agent.py            # メインループ。マルチエージェントパイプラインの制御
├── agent_state.py      # 役割別履歴管理、スクリーンショット履歴
├── mcp_manager.py      # MCPサーバーの管理。動的なツールの作成・実行・管理
├── memory_manager.py   # カテゴリ別メモリ管理 (Global/Engineering/Operation)
├── llm_client.py       # Gemini 専用クライアント。Native Function Calling対応
├── prompts.py          # 各役割（エージェント）のシステム指示定義
├── dashboard.py        # FastAPIを使用したWebダッシュボードサーバー
├── config.py           # 設定管理
├── logger.py           # ロギング設定
├── templates/          # ダッシュボードHTML
│   └── dashboard.html
├── workspace/          # エージェントが生成したツール（MCPサーバー）
├── history/            # チェックポイント（中断・再開用）
│   └── agent_checkpoint.json
├── logs/               # デバッグログ（自動ローテーション）
└── utils/              # ユーティリティモジュール
    └── vision.py       # スクリーンショット取得
```

## コアコンポーネント

### GameAgent (`agent.py`)

*   マルチエージェントパイプラインのオーケストレーション
*   `_execute_phase()`: 各エージェントのフェーズを実行。フェーズ内ループ対応
*   チェックポイントの保存・復元

### AgentState (`agent_state.py`)

*   **役割別履歴管理**: 各エージェントは自分の過去の履歴のみを参照
*   **グローバル履歴**: MemorySaver は全体の流れを把握するためにグローバル履歴を使用
*   **スクリーンショット履歴**: 直近3ターンの画面を保持

### MCPManager (`mcp_manager.py`)

*   `meta_manager` (仮想サーバー): ツール作成・編集・削除
*   `memory_manager` (仮想サーバー): カテゴリ別メモリ操作
*   `workspace/` 内のユーザー作成MCPサーバーの起動・管理

### LLMClient (`llm_client.py`)

*   Gemini API との通信
*   Native Function Calling 対応
*   ツール定義の動的設定

## Self-Coding アーキテクチャ

このシステムは、エージェントが「ツールを使う」だけでなく**「ツールを作る」**ことができるのが最大の特徴です。

1.  **ToolCreator** がタスクに必要なツールを分析
2.  `meta_manager.create_mcp_server` で Python スクリプトを生成
3.  生成されたスクリプトは `workspace/` に保存され、即座にMCPサーバーとして起動
4.  **Operator** が新しいツールを使用してタスクを実行

これにより、予期せぬ問題に直面しても、自ら解決のためのツールを実装して乗り越えることが可能です。

## デバッグ

### ログの確認

*   コンソール出力: 各フェーズの思考とツール実行結果
*   `logs/` ディレクトリ: 詳細なデバッグログ
*   ダッシュボード: リアルタイムで思考と状態を監視

### チェックポイント

`history/agent_checkpoint.json` には以下が保存されます：
*   メモリ状態 (カテゴリ付き)
*   エージェント履歴
*   Ultimate Goal
*   タイムスタンプ

## License

MIT License
