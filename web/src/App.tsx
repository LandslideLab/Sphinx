import { HashRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from './components/Toast'
import { Layout } from './components/Layout'
import { Ambient } from './components/Ambient'
import { Queue } from './pages/Queue'
import { Decisions } from './pages/Decisions'
import { Metrics } from './pages/Metrics'
import { Policies } from './pages/Policies'

export default function App() {
  return (
    <ToastProvider>
      <Ambient />
      <HashRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Queue />} />
            <Route path="/decisions" element={<Decisions />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="/policies" element={<Policies />} />
          </Routes>
        </Layout>
      </HashRouter>
    </ToastProvider>
  )
}
