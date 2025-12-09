# LLM Gamer Agent

LLM Gamer Agent は、Google Gemini (Gemini 2.0 Flash Exp等) を活用し、コンピュータ画面上の情報を視覚的に認識しながら、自律的にタスクを実行したりゲームをプレイしたりするエージェントシステムです。

Model Context Protocol (MCP) アーキテクチャを採用しており、エージェント自身が必要に応じて Python スクリプト（MCPサーバー）を作成・実行し、能力を拡張していくことができます。

## 特徴

*   **Gemini Native**: Google Gemini 2.0 Flash Exp を使用し、高速な応答と強力なマルチモーダル処理を実現。
*   **視覚的認識 (Vision)**: 画面のスクリーンショットをリアルタイムで取得・解析し、状況を把握します。
*   **自律的なツール作成 (Self-Coding)**: タスク達成のために必要なツール（Pythonコード）をエージェント自身が生成し、即座に実行環境にデプロイして使用します。
*   **思考プロセス (Cognition)**: "Thought Chain" (CoT) により、行動の理由や計画を論理的に組み立てます。
*   **リアルタイムダッシュボード (Live GUI)**: エージェントの視界、思考、記憶、実行ログをWebブラウザ上でリアルタイムに監視できるモダンなGUIを提供します。
*   **中断と再開 (Resumability)**: 過去の履歴からエージェントの状態を復元し、タスクを再開することができます。
*   **記憶管理 (Memory)**: 重要な情報やタスクの状態を記憶として保持し、長期的なタスク遂行をサポートします。

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
    GEMINI_MODEL=gemini-2.0-flash-exp
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
*   **Active Memories**: 現在保持している記憶。
*   **Cognitive Stream**: エージェントの思考内容（Thought）。
*   **Tool Activity**: 実行されたツールとその結果のログ。
*   **User Input**: エージェントからの質問や、タスクの指示入力画面。

## 使用可能なライブラリ

エージェントが自律的にツール（Pythonスクリプト）を作成する際、以下のライブラリを使用するように制限・制御されています。これにより、安全かつ効率的なコード生成を促します。

*   **基本操作**: `time`, `json`, `re` 等の標準ライブラリ
*   **画面操作**: `pyautogui`, `pydirectinput` (ゲーム用), `pygetwindow`
*   **画像認識**: `easyocr` (OCR), `pillow`, `cv2` (OpenCV), `mss` (高速キャプチャ), `numpy`
*   **システム**: `psutil`, `pyperclip`, `pywin32`

## ディレクトリ構成

*   `agent.py`: エージェントのメインループ。思考と意思決定を担当。
*   `mcp_manager.py`: MCPサーバーの管理。動的なツールの作成・実行・管理。
*   `dashboard.py`: FastAPIを使用したWebダッシュボードサーバー。
*   `llm_client.py`: Gemini や LM Studio との通信を抽象化するクライアント。
*   `config.py`: 設定管理。
*   `workspace/`: エージェントが生成したツール（MCPサーバー）が保存される場所。
*   `history/`: エージェントの状態やメモリのチェックポイント（中断・再開用）。
*   `logs/`: 生のLLMレスポンスなどのデバッグログ（自動ローテーション）。

## アーキテクチャについて

このシステムは、エージェントが「ツールを使う」だけでなく**「ツールを作る」**ことができるのが最大の特徴です。
`meta_manager` という管理モジュールを通じて、エージェントは `workspace` フォルダ内に新しいPythonスクリプトを作成し、即座にそれをMCPサーバーとして起動・接続します。これにより、予期せぬ問題に直面しても、自ら解決のためのツールを実装して乗り越えることが可能です。

## License

MIT License
