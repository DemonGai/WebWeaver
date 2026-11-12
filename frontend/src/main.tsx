import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import './index.css'

const container = document.getElementById('root')
if (!container) throw new Error('#root 节点不存在')

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      {/* 登录态要在路由之上：守卫和页面都要读它 */}
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
