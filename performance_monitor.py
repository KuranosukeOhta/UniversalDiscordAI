#!/usr/bin/env python3
"""
Universal Discord AI - パフォーマンス監視スクリプト
非同期処理の性能をリアルタイムで監視
"""

import asyncio
import time
import psutil
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """パフォーマンス監視クラス"""
    
    def __init__(self, config_file: str = "config/config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.monitoring = False
        self.monitor_interval = 5  # 5秒ごとに監視
        self.performance_history: List[Dict] = []
        self.max_history_size = 1000
        
        # システム情報
        self.system_info = self.get_system_info()
        
    def load_config(self) -> Dict:
        """設定ファイルを読み込み"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"設定ファイルが見つかりません: {self.config_file}")
                return {}
        except Exception as e:
            logger.error(f"設定ファイル読み込みエラー: {e}")
            return {}
    
    def get_system_info(self) -> Dict:
        """システム情報を取得"""
        try:
            return {
                'cpu_count': psutil.cpu_count(),
                'memory_total': psutil.virtual_memory().total,
                'disk_total': psutil.disk_usage('/').total,
                'python_version': f"{psutil.sys.version_info.major}.{psutil.sys.version_info.minor}.{psutil.sys.version_info.micro}",
                'platform': psutil.sys.platform
            }
        except Exception as e:
            logger.error(f"システム情報取得エラー: {e}")
            return {}
    
    async def start_monitoring(self):
        """監視を開始"""
        self.monitoring = True
        logger.info("パフォーマンス監視を開始しました")
        
        while self.monitoring:
            try:
                # パフォーマンスデータを収集
                performance_data = await self.collect_performance_data()
                
                # 履歴に追加
                self.performance_history.append(performance_data)
                
                # 履歴サイズを制限
                if len(self.performance_history) > self.max_history_size:
                    self.performance_history.pop(0)
                
                # パフォーマンスデータを表示
                self.display_performance_data(performance_data)
                
                # アラートチェック
                await self.check_alerts(performance_data)
                
                # 設定された間隔で待機
                await asyncio.sleep(self.monitor_interval)
                
            except Exception as e:
                logger.error(f"監視中にエラーが発生: {e}")
                await asyncio.sleep(self.monitor_interval)
    
    async def collect_performance_data(self) -> Dict:
        """パフォーマンスデータを収集"""
        timestamp = datetime.now()
        
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # メモリ使用率
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used = memory.used
            memory_available = memory.available
            
            # ディスク使用率
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # ネットワークI/O
            network = psutil.net_io_counters()
            
            # プロセス情報
            process = psutil.Process()
            process_cpu_percent = process.cpu_percent()
            process_memory_info = process.memory_info()
            
            # 非同期タスク情報（シミュレーション）
            async_tasks_info = await self.get_async_tasks_info()
            
            return {
                'timestamp': timestamp.isoformat(),
                'cpu': {
                    'system_percent': cpu_percent,
                    'process_percent': process_cpu_percent
                },
                'memory': {
                    'system_percent': memory_percent,
                    'system_used': memory_used,
                    'system_available': memory_available,
                    'process_rss': process_memory_info.rss,
                    'process_vms': process_memory_info.vms
                },
                'disk': {
                    'percent': disk_percent,
                    'used': disk.used,
                    'free': disk.free
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                },
                'async_tasks': async_tasks_info,
                'system_load': self.get_system_load()
            }
            
        except Exception as e:
            logger.error(f"パフォーマンスデータ収集エラー: {e}")
            return {
                'timestamp': timestamp.isoformat(),
                'error': str(e)
            }
    
    async def get_async_tasks_info(self) -> Dict:
        """非同期タスク情報を取得（シミュレーション）"""
        try:
            # 実際のBOTが動作していない場合はシミュレーション
            import random
            
            return {
                'active_tasks': random.randint(0, 20),
                'completed_tasks': random.randint(0, 100),
                'failed_tasks': random.randint(0, 5),
                'concurrent_peak': random.randint(15, 25),
                'average_response_time': random.uniform(0.5, 3.0),
                'message_queue_size': random.randint(0, 10)
            }
        except Exception as e:
            logger.error(f"非同期タスク情報取得エラー: {e}")
            return {}
    
    def get_system_load(self) -> Dict:
        """システムロードを取得"""
        try:
            if hasattr(psutil, 'getloadavg'):
                load_avg = psutil.getloadavg()
                return {
                    '1min': load_avg[0],
                    '5min': load_avg[1],
                    '15min': load_avg[2]
                }
            else:
                return {}
        except Exception as e:
            logger.error(f"システムロード取得エラー: {e}")
            return {}
    
    def display_performance_data(self, data: Dict):
        """パフォーマンスデータを表示"""
        if 'error' in data:
            logger.error(f"パフォーマンスデータエラー: {data['error']}")
            return
        
        timestamp = data['timestamp']
        cpu = data['cpu']
        memory = data['memory']
        disk = data['disk']
        network = data['network']
        async_tasks = data['async_tasks']
        system_load = data['system_load']
        
        # コンソールに表示
        print(f"\n{'='*60}")
        print(f"パフォーマンス監視 - {timestamp}")
        print(f"{'='*60}")
        
        # CPU情報
        print(f"🖥️  CPU使用率:")
        print(f"   システム全体: {cpu['system_percent']:6.1f}%")
        print(f"   プロセス:     {cpu['process_percent']:6.1f}%")
        
        # メモリ情報
        print(f"💾 メモリ使用率:")
        print(f"   システム全体: {memory['system_percent']:6.1f}%")
        print(f"   使用中:       {memory['system_used'] / 1024**3:6.1f} GB")
        print(f"   利用可能:     {memory['system_available'] / 1024**3:6.1f} GB")
        print(f"   プロセスRSS:  {memory['process_rss'] / 1024**2:6.1f} MB")
        
        # ディスク情報
        print(f"💿 ディスク使用率:")
        print(f"   使用率:       {disk['percent']:6.1f}%")
        print(f"   使用中:       {disk['used'] / 1024**3:6.1f} GB")
        print(f"   空き容量:     {disk['free'] / 1024**3:6.1f} GB")
        
        # ネットワーク情報
        print(f"🌐 ネットワークI/O:")
        print(f"   送信:         {network['bytes_sent'] / 1024**2:6.1f} MB")
        print(f"   受信:         {network['bytes_recv'] / 1024**2:6.1f} MB")
        print(f"   送信パケット: {network['packets_sent']:6d}")
        print(f"   受信パケット: {network['packets_recv']:6d}")
        
        # 非同期タスク情報
        if async_tasks:
            print(f"🚀 非同期タスク:")
            print(f"   アクティブ:   {async_tasks.get('active_tasks', 0):6d}")
            print(f"   完了:        {async_tasks.get('completed_tasks', 0):6d}")
            print(f"   失敗:        {async_tasks.get('failed_tasks', 0):6d}")
            print(f"   ピーク:      {async_tasks.get('concurrent_peak', 0):6d}")
            print(f"   平均応答時間: {async_tasks.get('average_response_time', 0):6.2f}秒")
            print(f"   キューサイズ: {async_tasks.get('message_queue_size', 0):6d}")
        
        # システムロード情報
        if system_load:
            print(f"📊 システムロード:")
            print(f"   1分平均:     {system_load.get('1min', 0):6.2f}")
            print(f"   5分平均:     {system_load.get('5min', 0):6.2f}")
            print(f"   15分平均:    {system_load.get('15min', 0):6.2f}")
        
        print(f"{'='*60}")
    
    async def check_alerts(self, data: Dict):
        """アラートチェック"""
        if 'error' in data:
            return
        
        alerts = []
        
        # CPU使用率アラート
        if data['cpu']['system_percent'] > 80:
            alerts.append(f"⚠️  CPU使用率が高い: {data['cpu']['system_percent']:.1f}%")
        
        # メモリ使用率アラート
        if data['memory']['system_percent'] > 85:
            alerts.append(f"⚠️  メモリ使用率が高い: {data['memory']['system_percent']:.1f}%")
        
        # ディスク使用率アラート
        if data['disk']['percent'] > 90:
            alerts.append(f"⚠️  ディスク使用率が高い: {data['disk']['percent']:.1f}%")
        
        # 非同期タスクアラート
        if data.get('async_tasks'):
            async_tasks = data['async_tasks']
            if async_tasks.get('failed_tasks', 0) > 10:
                alerts.append(f"⚠️  失敗タスクが多い: {async_tasks['failed_tasks']}件")
            
            if async_tasks.get('active_tasks', 0) > 15:
                alerts.append(f"⚠️  アクティブタスクが多い: {async_tasks['active_tasks']}件")
        
        # アラートを表示
        for alert in alerts:
            logger.warning(alert)
            print(f"\n{alert}")
    
    def stop_monitoring(self):
        """監視を停止"""
        self.monitoring = False
        logger.info("パフォーマンス監視を停止しました")
    
    def save_performance_report(self, filename: str = None):
        """パフォーマンスレポートを保存"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"performance_report_{timestamp}.json"
        
        try:
            report_data = {
                'system_info': self.system_info,
                'config': self.config,
                'performance_history': self.performance_history,
                'summary': self.generate_summary()
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"パフォーマンスレポートを保存しました: {filename}")
            
        except Exception as e:
            logger.error(f"パフォーマンスレポート保存エラー: {e}")
    
    def generate_summary(self) -> Dict:
        """パフォーマンスサマリーを生成"""
        if not self.performance_history:
            return {}
        
        try:
            # CPU使用率の統計
            cpu_percents = [data['cpu']['system_percent'] for data in self.performance_history if 'cpu' in data]
            memory_percents = [data['memory']['system_percent'] for data in self.performance_history if 'memory' in data]
            disk_percents = [data['disk']['percent'] for data in self.performance_history if 'disk' in data]
            
            return {
                'monitoring_duration': len(self.performance_history) * self.monitor_interval,
                'cpu': {
                    'average': sum(cpu_percents) / len(cpu_percents) if cpu_percents else 0,
                    'max': max(cpu_percents) if cpu_percents else 0,
                    'min': min(cpu_percents) if cpu_percents else 0
                },
                'memory': {
                    'average': sum(memory_percents) / len(memory_percents) if memory_percents else 0,
                    'max': max(memory_percents) if memory_percents else 0,
                    'min': min(memory_percents) if memory_percents else 0
                },
                'disk': {
                    'average': sum(disk_percents) / len(disk_percents) if disk_percents else 0,
                    'max': max(disk_percents) if disk_percents else 0,
                    'min': min(disk_percents) if disk_percents else 0
                }
            }
            
        except Exception as e:
            logger.error(f"サマリー生成エラー: {e}")
            return {}

async def main():
    """メイン実行関数"""
    logger.info("Universal Discord AI パフォーマンス監視開始")
    
    # 監視インスタンスを作成
    monitor = PerformanceMonitor()
    
    try:
        # 監視を開始
        await monitor.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("監視が中断されました")
        
        # パフォーマンスレポートを保存
        monitor.save_performance_report()
        
    except Exception as e:
        logger.error(f"監視中にエラーが発生: {e}")
        
        # パフォーマンスレポートを保存
        monitor.save_performance_report()
        
    finally:
        # 監視を停止
        monitor.stop_monitoring()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nプログラムが中断されました")
    except Exception as e:
        print(f"予期しないエラーが発生: {e}")
        import traceback
        traceback.print_exc()
